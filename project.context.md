Sonna Development Report

This report documents the current state of the Sonna project and outlines a roadmap for implementing each phase of the assistant. The Sonna codebase is split into backend and frontend components, with clearly defined responsibilities and modular architecture. Throughout the implementation we leverage modern services such as Supabase for database storage, Pinecone for semantic memory, Celery/Temporal for scheduling, VAPI and Whisper for transcription, ElevenLabs for speech synthesis and OpenAI/Anthropic for reasoning.

Repository Overview

The sonna directory contains two main applications:

Component	Description
Backend (FastAPI)	Hosts REST endpoints for voice transcription, intent classification, reminders, memory storage/retrieval and text‑to‑speech. It reads environment variables from .env and initialises external clients (Supabase, Pinecone, ElevenLabs). Services like the LLM agent and scheduler are kept separate to encourage single responsibility.
Frontend (React Native + Expo)	Provides a mobile UI with a microphone button, chat bubbles and audio playback. Uses axios to communicate with the backend and expo‑av to play audio streams.
Prompts	Defines Sonna’s persona (system_prompt.txt) and JSON Schemas for function calling (functions_schema.json). These allow the LLM to return structured commands such as “reminder” or “note” with parsed arguments.
Docs	Contains a high‑level architecture overview.
Key Technologies & Dependencies
Backend

FastAPI – lightweight Python web framework used to create REST endpoints.

Uvicorn – ASGI server for running the backend.

Supabase – hosted Postgres with built‑in auth. The Supabase Python client is initialised with a URL and service key
medium.com
.

Pinecone – vector database for storing embeddings. The asynchronous SDK is recommended; create your index at startup using the lifespan pattern
pinecone.io
.

ElevenLabs – streaming text‑to‑speech API. The Python SDK returns a generator of audio chunks that can be sent to clients
elevenlabs.io
.

OpenAI / Anthropic – large language models for reasoning and planning. The function‑calling API supports JSON Schema definitions to validate arguments
medium.com
.

Celery / Temporal – job queues and schedulers used to send reminders at the right time. A Celery app can be set up with a broker and result backend using code similar to the TestDriven.io example
testdriven.io
.

Redis – typical broker for Celery tasks.

Frontend

React Native + Expo – cross‑platform mobile framework.

Axios – HTTP client for calling backend endpoints.

expo‑av – audio recording and playback library.

Phase‑by‑Phase Roadmap
Phase 1 – MVP (voice loop + reminders)

Transcription – Use VAPI + Whisper streaming to transcribe microphone audio. The VAPI API uses WebSocket transport; specify transport.provider as vapi.websocket and choose an audio format (e.g. PCM)
docs.vapi.ai
.

Intent Parsing – Send the transcribed text to the LLM along with function schemas. The model will call either create_reminder or create_note with structured arguments
medium.com
.

Reminders CRUD – Create, list and delete reminders in Supabase via REST endpoints. Use ISO datetime validation in the router.

TTS Streaming – Convert the assistant’s reply into speech using ElevenLabs and stream the result back to the client
elevenlabs.io
.

Mobile UI – Implement voice recording, send audio to the backend, display transcripts and play responses. For now a simple microphone button suffices; advanced streaming will come later.

Phase 2 – Adaptive Task Engine

Integrate Celery or Temporal for background job processing. Tasks include sending reminders at scheduled times and handling snoozes/reschedules. Use a broker such as Redis.

Extend the reminders model to store completion status and logs. Use this data to learn user behaviour (e.g. “always snoozes tasks at night”).

Implement push notifications (via Firebase or Expo) so users receive reminders even when the app is closed.

Phase 3 – Memory & Retrieval

Embed user notes and conversations using OpenAI’s embeddings API. Upsert these vectors into Pinecone and implement a /memory/search endpoint that queries similar memories.

Add a daily summarizer job that summarises notes and logs to Supabase. Use the LLM to produce a concise summary.

Phase 4 – Context & Behaviour Layer

Integrate external signals like Google Calendar events and device location/time. Use them to customise reminders (e.g. “You’re home – film that TikTok now”).

Learn patterns in task completion: if the user often reschedules a reminder, automatically adjust its next occurrence.

Update the system prompt dynamically based on current context (e.g. tone of conversation, location, time of day).

Phase 5 – Personality & Emotion

Perform tone analysis on the user’s voice or text (e.g. using prosody features or LLM sentiment analysis). Adjust the assistant’s phrasing accordingly.

Build a knowledge graph (“Sonna Memory Graph”) linking tasks, people and topics. Use this graph to generate more personalised suggestions.

Phase 6 – Mobile Polish & Deployment

Add a background listening toggle that starts/stops the microphone to save battery.

Use secure storage (e.g. Expo SecureStore) to store API keys on device.

Integrate analytics (Sentry, PostHog) for performance monitoring and crash reporting.

Deploy the backend to a cloud platform (Render or Fly.io) with SSL and WebSocket support. Use Docker or Buildpacks for consistent deployment.

Distribute the mobile app via TestFlight and Google Play for beta testing.

Next Steps

Fill Out .env – Acquire API keys for OpenAI, ElevenLabs, VAPI, Supabase and Pinecone. Copy the provided .env.example to .env and fill in the values.

Set Up Supabase – Create a new project in Supabase, enable Row Level Security and create a reminders table with columns id, content, time, context, created_at, completed.

Create Pinecone Index – If not already created, set up a Pinecone index (e.g. dimension 1536 for OpenAI embeddings) in the dashboard.

Run Backend & Frontend – Start both servers as described in the README. Use the Swagger UI to manually test endpoints before integrating the frontend.

Implement Real‑Time Audio Streaming – Once the stubbed endpoints work, implement WebSocket streaming for both microphone input and audio playback. Use the VAPI and ElevenLabs SDKs as described earlier.

Iterate & Extend – Proceed to Phase 2 tasks once the MVP is stable. Keep the code modular to simplify future feature additions.

Concluding Remarks

The Sonna project provides a blueprint for building a sophisticated personal assistant with off‑the‑shelf services. By following the phased roadmap and leveraging modern cloud APIs, you can incrementally deliver value to users while scaling up to more advanced capabilities such as context awareness and emotional intelligence. The current scaffolding lays the groundwork for rapid experimentation, and the included documentation links back to the relevant primary sources for deeper understanding and implementation details.