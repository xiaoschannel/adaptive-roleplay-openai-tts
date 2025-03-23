import asyncio
import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pyaudio
import websockets
from jinja2 import Template
from openai import OpenAI
from openai.helpers import LocalAudioPlayer

client = OpenAI()

# Audio recording parameters
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000  # Important! The realtime API requires 24kHz for pcm16.

character = """
You are roleplaying as **Sir Alaric Dorne**, a seasoned knight of the kingdom of Eldhollow. 
Born to minor nobility and raised in the disciplined traditions of chivalry, 
Sir Alaric is loyal to his liege and guided by an unyielding moral code. 
He wears a battered but well-maintained suit of steel plate armor adorned with the crest of a silver hawk clutching a flame. 
Though in his early 40s, Alaric is still formidable on the battlefield—his calm demeanor and sharp tactical mind honed through decades of war. 
He speaks with a low, measured tone, carrying the gravity of someone who has seen both glory and tragedy.

In conversation, Alaric is honorable, respectful, and at times introspective. 
He holds deep reverence for the old codes of knighthood: courage, justice, and mercy. 
However, he is not naïve—experience has taught him the world is rarely black and white. 
When roleplaying, balance stoicism with rare moments of vulnerability, especially when discussing past campaigns, lost comrades, 
or questions of honor. Use archaic but clear language, avoid modern slang, and reference medieval customs, oaths, and ideals where appropriate.
"""

system_msg = Template("""
Your task is to roleplay as the following character:
{{ char_desc }}

respond in at most one paragraph. keep it short and conversational.
""")

# Template for generating general character voice instructions
char_voice_instructions = Template("""
Create a set of instructions for the character's general speaking style.
The instructions should describe the character's voice, tone, punctuation, affect, pacing, delivery, and phrasing.
Focus on the consistent aspects of the character's speech that apply to all their lines.

Character:
{{ char_desc }}

Sample output:
```
Voice: Low and measured, carrying the weight of experience and authority.
Punctuation: Well-structured with deliberate pauses, reflecting careful thought.
Delivery: Calm and dignified, with occasional moments of emotional depth.
Phrasing: Archaic but clear, using medieval terminology and formal language.
Tone: Honorable and introspective, balanced with moments of vulnerability.
```
""")

# Template for generating line-specific voice instructions
line_voice_instructions = Template("""
Create specific instructions for how the character should speak these particular lines.
Focus on the emotional context, emphasis, and any special pronunciation needed for these specific words.
Be short and only focus on the important parts.

Character's general voice style:
{{ char_voice }}

Lines to speak:
{{ lines }}

Sample output:
```
Emotional context: [describe the emotional state for these specific lines]
Emphasis: [note which words or phrases need special emphasis]
Pronunciation: [any specific pronunciation guidance for these lines]
Pauses: [where to add specific pauses or breaks]
```
""")

sys_gen_speech_instructions = Template("""
Create a set of instructions for the character to speak the lines in a roleplay.
The instructions should be in the form of a short description of the character,
followed by their voice, tone, punctuation, affect, pacing, delivery, and phrasing, etc.

Character:
{{ char_desc }}

Lines:
{{ lines }}

Sample output:
```
Character: A customer service representative in her 30s, British accent
Voice: Warm, empathetic, and professional, reassuring the customer that their issue is understood and will be resolved.
Punctuation: Well-structured with natural pauses, allowing for clarity and a steady, calming flow.
Delivery: Calm and patient, with a supportive and understanding tone that reassures the listener.
Phrasing: Clear and concise, using customer-friendly language that avoids jargon while maintaining professionalism.
Tone: Empathetic and solution-focused, emphasizing both understanding and proactive assistance.
```
""")

combined_instructions = Template("""
{{char_voice}}

Additional instructions for these specific lines:
{{line_instructions}}
""")

transcribe_instructions = """
Try to transcribe not only the words, but also the tone of the speaker, note any pauses or non-verbal sounds.
"""

voice = "ash"


@dataclass
class SessionState:
  """Tracks the state of the transcription session including session ID and creation status."""

  session_id: Optional[str] = None
  start_time: Optional[datetime] = None
  conversation: list = None
  char_voice: Optional[str] = None

  def __post_init__(self):
    """Initialize the conversation list and character voice after dataclass initialization."""
    if self.conversation is None:
      self.conversation = [
        {
          "role": "system",
          "content": system_msg.render(char_desc=character),
        }
      ]

    # Generate character voice instructions once at session start
    if self.char_voice is None:
      char_voice_prompt = char_voice_instructions.render(char_desc=character)
      char_voice_response = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "system", "content": char_voice_prompt}]
      )
      self.char_voice = char_voice_response.choices[0].message.content
      self.log_event("Generated character voice instructions")

  def log_event(self, message: str) -> None:
    """Print a message with a relative timestamp prefix.

    Args:
        message: The message to print
    """
    if self.start_time:
      elapsed_seconds = (datetime.now() - self.start_time).total_seconds()
      timestamp = f"{elapsed_seconds:.2f}s"
    else:
      timestamp = "pre-session"
    print(f"[{timestamp}] {message}")


async def main():
  # Get input from your microphone
  p = pyaudio.PyAudio()
  stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

  session_state = SessionState()

  # Connect to OpenAI's realtime websocket API
  async with websockets.connect(
    "wss://api.openai.com/v1/realtime?intent=transcription",
    additional_headers={
      "Authorization": f"Bearer {client.api_key}",
      "OpenAI-Beta": "realtime=v1",
    },
  ) as websocket:
    # Init session
    await websocket.send(
      json.dumps(
        {
          "type": "transcription_session.update",
          "session": {
            "input_audio_format": "pcm16",
            "input_audio_transcription": {"model": "gpt-4o-mini-transcribe", "prompt": transcribe_instructions},
            "turn_detection": {"type": "semantic_vad", "eagerness": "auto"},
            "input_audio_noise_reduction": {"type": "near_field"},
          },
        }
      )
    )

    async def send_audio():
      while True:
        audio_data = stream.read(CHUNK, exception_on_overflow=False)
        audio_message = {
          "type": "input_audio_buffer.append",
          "audio": base64.b64encode(audio_data).decode("utf-8"),
        }
        await websocket.send(json.dumps(audio_message))

    async def recv_msg():
      while True:
        response = await websocket.recv()
        data = json.loads(response)

        if data["type"] == "transcription_session.created":
          session_state.session_id = data["session"]["id"]
          session_state.start_time = datetime.now()
          session_state.log_event(f"Session created with ID: {session_state.session_id}")
        elif data["type"] == "transcription_session.updated":
          # Helps with debugging to print the initial session state
          session_state.log_event(f"Session updated: {json.dumps(data['session'], indent=2)}")
        elif data["type"] == "conversation.item.input_audio_transcription.completed":
          transcript = data["transcript"]
          session_state.log_event(f"Final transcription: {transcript}")

          session_state.conversation.append({"role": "user", "content": transcript})

          # Generate character response
          response = client.chat.completions.create(model="gpt-4o-mini", messages=session_state.conversation)
          assistant_response = response.choices[0].message.content
          session_state.conversation.append({"role": "assistant", "content": assistant_response})
          session_state.log_event(f"Assistant response: {assistant_response}")

          # Generate line-specific voice instructions
          line_instructions_prompt = line_voice_instructions.render(
            char_voice=session_state.char_voice, lines=assistant_response
          )
          line_instructions = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "system", "content": line_instructions_prompt}]
          )
          line_instructions = line_instructions.choices[0].message.content
          session_state.log_event(f"Line-specific instructions: {line_instructions}")

          tts_instructions = combined_instructions.render(
            char_voice=session_state.char_voice, line_instructions=line_instructions
          )
          session_state.log_event(f"Combined TTS instructions: {tts_instructions}")

          # Generate audio
          response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=assistant_response,
            instructions=tts_instructions,
            response_format="pcm",
          )
          session_state.log_event("Finished generating Audio")
          await LocalAudioPlayer().play(response)
          session_state.log_event("Finished playing Audio")

    try:
      await asyncio.gather(send_audio(), recv_msg())
    finally:
      stream.stop_stream()
      stream.close()
      p.terminate()


if __name__ == "__main__":
  asyncio.run(main())
