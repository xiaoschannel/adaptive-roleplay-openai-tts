# Emotionally Adaptive Roleplay with OpenAI 4o-mini-tts PoC

This is a program that allows you to have a conversation with a character whose voice adapts to their emotions.

# Setup:

```
cp .env.example .env
# fill in your openai api key
pip install -r requirements.txt
```

# To Run:

```bash
python adaptive_roleplay.py
```

When the program says "Session created with ID: <id>", you can start talking.

# Why?
OpenAI `gpt-4o-mini-tts` allows you to [instruct the TTS model how it speaks](https://www.openai.fm/). However, speaking the same way for an entire passage is not engaging or realistic, as argued by [the Sesame team](https://www.sesame.com/research/crossing_the_uncanny_valley_of_voice).

While `gpt-4o-mini-tts` has some impressive capacity to adapt how it speaks based on what is being spoken (try a sentence like `It's so boring today... Wait, what's that? My pants are on fire!`). In my opinion, it was not quite on par with the Sesame demo.

In my experiments, sometimes even `CSM-1B`, their open-weights model, could produce better results(not to mention you can use voice prompts).

Trying to improve the results from `gpt-4o-mini-tts`, I found that you can get much further by tweaking your instructions according to the text (e.g. `start calm and bored, but start to scream when you find out your pants are on fire`). 

It would be a pain to do that manually for every single line. "But we can have an AI do that!" I thought.

So here's a proof-of-concept trying to close that gap: it generates a set of instructions on-the-fly, specific to what's being said, to produce an adaptive yet consistent voice.

# Technical Details

- First, a **character voice instruction** is generated based on the character description with `gpt-4o`.
- When the conversation start, it streams audio from your microphone to the transcription mode of the OpenAI Realtime API with `gpt-4o-mini-transcribe`.
  - The realtime API provides noise cancellation, detects when you have done talking (VAD), and converts the audio to text.
- We then use `gpt-4o-mini` to generate **lines** responding to what you've said to the character, based on the character description and the conversation history.
- Then we generate a **response voice instruction** with `gpt-4o-mini` for those particular **lines**.
- We then combine the **character voice instruction** and the **response voice instruction** to generate the audio for the response with `gpt-4o-mini-tts`.

# Limitations

## Latency
Currently we're operating at 30~60 seconds per turn.
- In my tests, `gpt-4o-mini-transcribe` is quite slow. My best guess:
  - I am in Japan and their servers are in the US.
  - pcm16 is slow compared to g711u or g711a.
- While `gpt-4o-mini-tts` operates faster than realtime, it currently doesn't seem to support streaming, so we're playing audio after its entirety was generated. 
  - surely with "gpt" in the name, it's not a diffusion model... right?
- Of course, you can also achieve this with the realtime API by repeatedly sending `session.update`s, which is built for -- wait for it -- realtime applications (you'd still need to render the **response voice instructions** on the fly though). But having an LLM allows for better intelligence, which I believe is better for roleplaying, where adaptive emotions in voice is important.

## Roleplaying
- No user character config.
- No narrator.

These can probably be achieved by having 4o-mini generate response in a list of json objects containing character id and lines -- This would also be a great improvement over what is on https://openai.fm/ and allows parallelization.

- No RAG for world lore or character backstory.
- No automatic voice selection

## Prompting
- Prompting `gpt-4o-mini-tts` is still quite new and not well documented. Here's what I found:
  - You can prompt "how it speaks" either in the voice instruction or in the lines(by adding notes in brackets, and telling it to follow the notes instead of speaking them in the instructions).
  - Neither of these prevents the model from speaking what is in the brackets occasionally.
- There could be better prompts to create the **character voice instructions** and **response voice instructions**. All I did was trial and error, and some official instructions as output format/one-shot example.