<div align="center">

<img src="docs/logo.svg" width="72" alt="Neural Hub Institute logo" />

# Neural Hub Institute

**An AI-powered learning platform where students learn from real teachers, and AI does the heavy lifting around them.**

Teachers create courses with an AI assistant, teach live 1-to-1 classes, and send quizzes.<br/>
Students book classes, learn with an AI Teacher, ask an AI assistant their doubts, and earn verifiable certificates.<br/>
Admins approve teachers, handle payments and refunds, and issue certificates recorded on the Polygon blockchain.

![Next.js](https://img.shields.io/badge/Next.js-16-000?logo=nextdotjs)
![React](https://img.shields.io/badge/React-18-149eca?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178c6?logo=typescript&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind-4-38bdf8?logo=tailwindcss&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.11-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-SQLAlchemy%202-336791?logo=postgresql&logoColor=white)
![LiveKit](https://img.shields.io/badge/LiveKit-WebRTC-ff6b35)
![Polygon](https://img.shields.io/badge/Polygon-certificates-8247e5?logo=polygon&logoColor=white)

</div>

> **About this repository.** Neural Hub Institute is a product I build as an AI & Full-Stack Developer at CarbonRepro.
> The full source is private. This public repository is a **showcase**: it explains the whole system end to end
> (architecture, data flow, AI design, decisions), shows the product through screenshots, and includes a
> hand-picked set of real source files (frontend components and the core AI / business logic) so you can read the code.
> Secrets, the database, deployment config and most modules are not included.

---

## Contents

1. [The product in one minute](#1-the-product-in-one-minute)
2. [Screenshots](#2-screenshots)
3. [Features by portal](#3-features-by-portal)
4. [System architecture](#4-system-architecture)
5. [How the main flows work](#5-how-the-main-flows-work)
6. [The AI layer](#6-the-ai-layer)
7. [Tech stack](#7-tech-stack)
8. [Project structure](#8-project-structure)
9. [Code in this repository](#9-code-in-this-repository)
10. [Engineering practices](#10-engineering-practices)
11. [Security](#11-security)
12. [Deployment](#12-deployment)
13. [My role](#13-my-role)
14. [Roadmap](#14-roadmap)

---

## 1. The product in one minute

Most learning apps are either "AI only" (a chatbot that teaches) or "human only" (a tutor marketplace). Neural Hub
Institute combines both: **the teacher stays in charge, and AI handles everything around the teacher.**

| Who | What they do | Where AI helps |
| --- | --- | --- |
| **Student** | Finds a teacher, sends a request, books 1-hour live classes, watches lectures, takes class quizzes, earns a certificate | AI Teacher (avatar that teaches the course), "Ask AI" doubt solver, AI class notes, learning-path tracking |
| **Teacher** | Accepts requests, builds courses, teaches live, marks outcomes, sends progress reports | AI course builder (plan → notes → quiz drafts), daily brief, request fit score, at-risk students, report writer |
| **Admin** | Approves teachers, moderates reviews, handles payments, refunds and payouts, issues certificates | System health, AI usage and cost, audit log |

**Size of the codebase (private repo):** 101 pages · ~400 API endpoints · ~55k lines of TypeScript · ~33k lines of Python · 56 backend test files.

---

## 2. Screenshots

Screens are from a local run with demo accounts (Ayesha = student, Hamza = teacher) at 1440 × 900.
Every page is designed to fit **one screen without scrolling**.

### Sign up and sign in
| Sign up | Sign in (one login for every role) |
| --- | --- |
| ![Sign up](screenshots/01-signup.png) | ![Sign in](screenshots/02-login.png) |

### Student portal
| Home dashboard | Profile card (hover) |
| --- | --- |
| ![Student dashboard](screenshots/10-student-dashboard.png) | ![Profile card](screenshots/11-student-profile-card.png) |

| Find tutors | Tutor profile + request form |
| --- | --- |
| ![Find tutors](screenshots/12-find-tutors.png) | ![Tutor profile](screenshots/13-tutor-profile.png) |

| My requests | Live sessions (book a slot) |
| --- | --- |
| ![My requests](screenshots/14-my-requests.png) | ![Live sessions](screenshots/15-live-sessions.png) |

| Progress (live study time) | Payments and receipts |
| --- | --- |
| ![Progress](screenshots/16-progress.png) | ![Payments](screenshots/17-payments.png) |

| Certificates | Help & Support |
| --- | --- |
| ![Certificates](screenshots/18-certificates.png) | ![Help](screenshots/19-help-support.png) |

| Settings |  |
| --- | --- |
| ![Settings](screenshots/20-settings.png) |  |

### Teacher portal
| Dashboard | Profile card with Tutor ID |
| --- | --- |
| ![Tutor dashboard](screenshots/30-tutor-dashboard.png) | ![Tutor card](screenshots/31-tutor-profile-card.png) |

| Requests (real student data) | Schedule + weekly availability |
| --- | --- |
| ![Requests](screenshots/32-tutor-requests.png) | ![Schedule](screenshots/33-tutor-schedule.png) |

| My students | AI course assistant |
| --- | --- |
| ![Students](screenshots/34-tutor-students.png) | ![AI assistant](screenshots/35-tutor-ai-assistant.png) |

| Reports & analytics | Earnings & wallet |
| --- | --- |
| ![Reports](screenshots/36-tutor-reports.png) | ![Earnings](screenshots/37-tutor-earnings.png) |

| Profile & settings | Live classes (Meet) |
| --- | --- |
| ![Tutor settings](screenshots/38-tutor-settings.png) | ![Meet](screenshots/39-meet-home.png) |

### Admin
![Admin login](screenshots/40-admin-login.png)

---

## 3. Features by portal

### Student
- **Find tutors:** search by name, subject or topic; tutor profile with rate, hours, languages, reviews.
- **Requests:** send a topic + level + message to a teacher; see when it was sent and when it was accepted.
- **Live sessions:** the teacher's weekly hours become 1-hour slots; free slots only; pay and book (test payment mode); cancel before start for a refund; add to calendar.
- **Live classes:** WebRTC classroom (LiveKit) with chat, whiteboard, raise hand, captions/translation and **AI class notes** after the class.
- **Courses and lectures:** teacher courses with lectures, video courses (free previews, buy, continue where you stopped).
- **AI Teacher:** an avatar teacher that teaches the teacher's course in blocks, checks understanding and adapts.
- **Ask AI ("Owl"):** doubt solver for any subject; also finds teachers, lectures and classes from plain words (English or Roman Urdu).
- **Quizzes:** class quizzes sent by the teacher, marked on the server.
- **Progress:** study time per day (week / month), quiz scores, calendar; updates live.
- **Learning path:** home card that walks the student's real course steps (joined → lectures → quiz → classes → certificate).
- **Certificates:** request → teacher review → admin approval → certificate with QR code, HMAC signature and on-chain fingerprint; public verify page.
- **Payments, Help & Support (tickets + help articles), Settings, Student ID.**

### Teacher
- **Dashboard:** today's sessions, new requests, active students, quiz average, schedule, **AI daily brief** (read aloud), student journey funnel, this month.
- **Requests:** approve/reject with the student's real data (quiz average, study time this week, classes) and an **AI fit score**.
- **Schedule:** next 7 days, booked/free slots, weekly availability editor, class outcomes (completed / no-show) and wrap-up notes.
- **AI Assistant:** create a course from a topic or from your own files → AI writes the lecture plan → you approve → AI writes notes, lesson material and one quiz draft per lecture → you approve the quiz.
- **My students:** per-student progress, at-risk flags with reasons, practice assignments.
- **Reports:** sessions, earnings, attendance, rating, charts; AI-written **progress reports** you edit and send.
- **Lectures, reviews, certificates (recommend a student), earnings & wallet, payouts, messages, support, profile & settings.**

### Admin
- Teacher approval with documents, students, courses, reviews moderation, payments, refunds and payouts.
- Certificate requests and blockchain status, reports, support tickets, notifications.
- Roles and permissions, two-factor login (TOTP), audit log, AI voice and model settings.

---

## 4. System architecture

```mermaid
flowchart LR
  subgraph Client["Browser"]
    S["Student portal"]
    T["Teacher portal"]
    A["Admin portal"]
    M["Meet: live classroom"]
  end

  subgraph FE["Next.js 16 · App Router · Vercel"]
    UI["React 18 + TypeScript<br/>Tailwind 4 · Lucide · Framer Motion"]
  end

  subgraph BE["FastAPI backend · Python 3.11"]
    AUTH["auth · roles · sessions"]
    PORTAL["portal · booking · payments"]
    TUTOR["tutor · courses · lectures"]
    CERT["certificates · signing · evidence"]
    AI["AI layer<br/>LLM gateway · AI Teacher · Owl · notes"]
    ADMIN["admin · audit · 2FA"]
  end

  DB[("PostgreSQL<br/>SQLAlchemy 2")]
  LLM["LLM providers<br/>Gemini · Groq · OpenRouter · Mistral · Ollama"]
  LK["LiveKit Cloud<br/>WebRTC"]
  CHAIN["Polygon<br/>certificate registry"]
  AV["Avatar engine<br/>LiteAvatar + edge-tts"]

  S & T & A --> UI
  M --> LK
  UI -- "REST / JSON" --> AUTH & PORTAL & TUTOR & CERT & AI & ADMIN
  AUTH & PORTAL & TUTOR & CERT & AI & ADMIN --> DB
  AI --> LLM
  AI --> AV
  CERT --> CHAIN
  PORTAL -- "room tokens" --> LK
```

**Design principles**

- **One backend, many modules.** Each feature is a FastAPI module (`auth`, `portal`, `tutor`, `courses`, `certificates`, `meet`, `professor`, `owl`, `payments`, `admin`, …) with its own models, router and tests.
- **The server is the source of truth.** Slots, payments, quiz marking, certificate eligibility and refunds are decided on the server, never in the browser.
- **AI never decides alone.** Rules (pure Python) decide *what* happens; the LLM decides only *how to say it*. Teachers approve every AI-made plan and quiz.
- **Every AI call goes through one gateway** with provider fallback, JSON validation and logging (see [section 6](#6-the-ai-layer)).
- **Works without AI.** If every provider is down, the app still runs: fallbacks are rule-based text, cached results, or "AI is not available right now".

---

## 5. How the main flows work

### 5.1 From request to certificate

```mermaid
sequenceDiagram
  autonumber
  actor St as Student
  actor Te as Teacher
  participant API as FastAPI
  participant AI as AI layer
  actor Ad as Admin

  St->>API: send request (topic, level, message)
  API->>AI: fit score (subject, capacity, hours, student activity)
  Te->>API: approve request
  Te->>AI: build course (plan → notes → quiz drafts)
  Te->>API: approve plan and quizzes
  St->>API: book a free slot + pay (test mode)
  St->>Te: live class (LiveKit)
  API->>AI: class transcript → AI class notes
  Te->>API: mark outcome, send class quiz
  St->>API: take quiz (marked on server)
  St->>API: request certificate (when eligible)
  Te->>API: recommend + grade
  Ad->>API: approve → certificate signed (HMAC) and recorded on Polygon
  St->>St: share link / QR → public verify page
```

### 5.2 Booking without double booking (`backend/modules/portal/booking.py`)

1. The teacher's weekly hours (in the teacher's time zone) are cut into 1-hour slots for the next 14 days.
2. A slot is **free** only if nothing uses that hour: another student's class, the teacher's group or instant class, a day off, or another class of the same student.
3. A slot must start at least 60 minutes from now; past slots are closed.
4. Booking is **only** done on the server under a **per-teacher lock**, and the slot is checked again inside the lock, so two students pressing the same slot at the same moment cannot both get it.
5. One accepted request = one class. Cancelling before the start gives the request back and starts a refund.

### 5.3 Live progress (`ProgressView.tsx`, `StudyTimer.tsx`, `meet/router.py`)

- `StudyTimer` adds **one minute per active minute** on learning pages (tab visible + recent input, or media playing).
- Live-class time counts **only the minutes the student was really in the room**: join/leave records are merged (a rejoin after a dropped connection counts once) and capped at the class length.
- The page reloads every minute and when the tab gets focus; week = Sunday–Saturday, month = calendar month.

### 5.4 Certificates you can verify (`certificates/*`)

- **Eligibility** is computed from evidence: lectures done, class quizzes passed, classes attended (minimum set by config).
- The payload is hashed (**SHA-256**) and signed with **HMAC**; any change breaks the signature.
- In blockchain mode only the **fingerprint** (no personal data) is written to a registry contract on **Polygon**; the verify page shows the transaction.

---

## 6. The AI layer

```mermaid
flowchart TB
  F["Feature code<br/>(teach, notes, report, fit, brief…)"] --> G["LLM Gateway<br/>one door for every call"]
  G --> R["Model router<br/>provider order per task"]
  R --> P1["Gemini"] & P2["Groq"] & P3["OpenRouter"] & P4["Mistral"] & P5["Ollama (local)"]
  G --> V{"JSON valid for<br/>the Pydantic schema?"}
  V -- "no" --> RT["retry once with a stricter instruction,<br/>then next provider"]
  V -- "yes" --> OUT["typed result"]
  G --> CB["circuit breaker<br/>(skip providers that keep failing)"]
  G --> LOG["recorder: every attempt,<br/>latency, cost → llm_calls"]
```

| Piece | What it does | File |
| --- | --- | --- |
| **LLM Gateway** | Single entry point; fallback across providers, JSON mode, Pydantic validation, retry, circuit breaker, per-call logging | `backend/modules/professor/llm/gateway.py`, `providers.py` |
| **Pedagogy policy** | The AI Teacher's "brain" as pure functions: decides *what* to do next (introduce, explain, check, hint, remediate, encourage, speed up) with a logged reason | `backend/modules/professor/core/policy.py` |
| **Lesson flow** | Teaches in blocks of up to 3 topics → review → MCQs → short written answers; a wrong answer re-teaches in a new way, 3 wrong = marked weak | `backend/modules/professor/core/flow.py` |
| **Prompts** | Versioned prompt templates for teaching turns | `backend/modules/professor/core/prompts.py` |
| **Course builder** | Background pipeline: plan → deep notes per lecture → lesson material + checked question bank → one quiz draft per lecture; teacher can stop and keep what's made | `backend/modules/courses/pipeline.py` |
| **Fact-check pass** | A second model acts as a strict examiner and only replaces exact wrong sentences | `backend/modules/syllabus/fact_check.py` |
| **Owl intent** | Understands what the student wants (study question, find teachers, lectures, groups, help, support) from plain words in English or Roman Urdu, **without AI** (fast and testable) | `backend/modules/owl/intent.py`, `lesson.py` |
| **AI class notes** | Speech pieces → Groq Whisper transcript → summary, key points, terms, Q&A, homework and a 5-question quiz | `backend/modules/meet/notes.py` |
| **Teacher AI** | Daily brief, at-risk score with reasons, request fit score, progress-report writer | `backend/modules/tutor/ai.py` |

---

## 7. Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 18, TypeScript, Tailwind CSS 4, Framer Motion, Lucide icons, React Markdown + KaTeX (math), QR codes |
| Live classes | LiveKit (WebRTC) — LiveKit Cloud, `@livekit/components-react` |
| Backend | FastAPI, Pydantic 2, SQLAlchemy 2, Uvicorn |
| Database | PostgreSQL (psycopg 3) |
| AI | Google Gemini, Groq (LLM + Whisper speech-to-text), OpenRouter, Mistral, Ollama (local), edge-tts (voice), LiteAvatar (talking avatar) |
| Blockchain | Polygon, web3.py and a small Node.js signer, certificate registry contract |
| Testing | pytest (56 test files), Playwright (browser checks), TypeScript strict build |
| DevOps | GitHub organization + pull-request reviews, GitHub Actions → Vercel (frontend), environment-based config |

---

## 8. Project structure

<details>
<summary><b>Full project tree (private repo)</b></summary>

```
neural-hub/
├── frontend/                      Next.js 16 app
│   ├── app/                       routes (App Router)
│   │   ├── login · signup · forgot · continue          one login for every role
│   │   ├── student/(portal)/      dashboard, courses, ai-teacher, ask, assessments, progress,
│   │   │                          tutors, requests, messages, sessions, live, lectures,
│   │   │                          certificates, payments, support, settings
│   │   ├── tutor/                 dashboard, requests, students, schedule, assistant, lectures,
│   │   │                          reviews, certificates, messages, reports, earnings, support, settings
│   │   ├── admin/(panel)/         dashboard, tutors, students, courses, certificates, payments,
│   │   │                          reviews, reports, support, admins, audit, settings, voice
│   │   ├── meet/[sessionId]/      live classroom + AI notes
│   │   └── verify/[id]/           public certificate verification
│   ├── components/
│   │   ├── student/  tutor/  admin/   one folder per portal, one sub-folder per page
│   │   ├── meet/  owl/  professor/    live classes, Ask AI, AI Teacher
│   │   └── shared/  support/  auth/   reused UI
│   ├── lib/                       typed API clients (one per backend module), auth, store, hooks
│   └── types/
├── backend/                       FastAPI
│   ├── main.py                    app + routers
│   ├── core/                      config, db, llm loader, mailer, money, public IDs, subjects
│   ├── modules/
│   │   ├── auth/                  accounts, sessions, email codes, roles
│   │   ├── portal/                student state, booking, booking assistant
│   │   ├── tutor/                 profiles, requests, sessions, AI (brief, fit, risk, reports)
│   │   ├── courses/  lectures/    teacher courses, AI pipeline, quizzes, video courses
│   │   ├── professor/             AI Teacher: core (policy, flow, session, memory), llm gateway,
│   │   │                          content builder, evaluation, voice (STT/TTS)
│   │   ├── owl/  solver/          Ask AI assistant
│   │   ├── meet/                  live classes, LiveKit tokens, notes, translation
│   │   ├── certificates/          evidence, signing, blockchain, requests
│   │   ├── payments/              checkout (test mode), refunds, wallet, payouts
│   │   ├── admin/                 roles, 2FA, audit, enforcement
│   │   └── marketplace/ support/ reminders/ media/ search/ settings/ avatar/ …
│   └── tests/                     pytest suites (admin, professor, avatar)
├── avatar/                        LiteAvatar engine (talking-head video)
└── livekit/                       local LiveKit config (dev)
```
</details>

---

## 9. Code in this repository

These are real files from the private repo, copied as-is (no secrets; all keys come from environment variables).

**Frontend** (`src/frontend`)

| File | Why it is interesting |
| --- | --- |
| `components/student/dashboard/v3/LearningPath.tsx` | Turns the student's certificate evidence into 5 steps; animated line-art path; refreshes every minute and on tab focus |
| `components/student/dashboard/v3/DashboardV3.tsx`, `DashboardView.tsx` | One-screen dashboard; "Today" feed built from live classes, open quizzes and the next lecture |
| `components/student/sessions/SessionsView.tsx`, `SlotPicker.tsx` | Day pills → time grid → checkout; upcoming/history with "See more" |
| `components/student/progress/ProgressView.tsx`, `StudyTimer.tsx` | Week/month charts and the study-minute timer |
| `components/student/layout/ProfileMenu.tsx` | Hover/focus profile card with Student ID (keyboard accessible) |
| `components/tutor/dashboard/TutorDashboard.tsx` | Teacher dashboard: stats, schedule, AI daily brief with text-to-speech, journey funnel |
| `lib/certRequests.ts`, `lib/routes.ts` | Typed API client and central route map |

**Backend / AI logic** (`src/backend`)

| File | Why it is interesting |
| --- | --- |
| `modules/professor/llm/gateway.py`, `providers.py` | LLM gateway: fallback, JSON validation, retry, circuit breaker, logging |
| `modules/professor/core/policy.py`, `flow.py`, `prompts.py` | AI Teacher decision rules and block-based lesson flow |
| `modules/courses/pipeline.py` | Background AI course builder with stop/keep |
| `modules/syllabus/fact_check.py` | Second-model fact check with exact-match corrections |
| `modules/owl/intent.py`, `lesson.py` | Intent detection without AI; Ask-AI answers |
| `modules/meet/notes.py` | AI class notes from the live-class transcript |
| `modules/tutor/ai.py` | Daily brief, at-risk score, fit score, progress reports |
| `modules/portal/booking.py` | Slot planner + race-safe booking |
| `modules/certificates/evidence.py`, `signing.py`, `blockchain.py` | Eligibility rules, HMAC signing, Polygon registry |
| `core/llm.py` | Shared LLM client loader |

---

## 10. Engineering practices

- **Plan → design → build → verify.** Every screen is designed on a canvas first, approved, then implemented; backend changes are planned together with the frontend that needs them.
- **AI-assisted, human-checked.** I use Claude / Claude Code for implementation; every change is reviewed as a diff, type-checked, built, and tested in a real browser before it ships.
- **Tests.** pytest suites cover booking, certificates, blockchain, auth, admin roles and 2FA, payments and the AI Teacher; Playwright scripts check pages at 1440 × 900 for layout, console errors and failed requests.
- **Small, reversible deliveries.** Each change is a numbered version with a backup of the files it replaces, so anything can be rolled back.
- **Team workflow.** The repo lives in a GitHub organization; a frontend teammate works on a fork and every pull request is reviewed before merge.

## 11. Security

- One login for every role (email + password or Google). Sessions use a random 256-bit token; only its hash is stored, it expires after 30 days and is revoked on log-out or password change.
- Passwords hashed with **scrypt** and a random salt; email verification codes; role checks on every protected route.
- Admin login with **TOTP two-factor**, role-based permissions and an **audit log** of admin actions.
- All secrets (DB, AI keys, signing key, wallet key) come from environment variables and are never committed.
- Payments run in **test mode**; card numbers and CVV are never stored (only the last 4 digits for receipts).
- Certificates: HMAC-signed payloads; only a hash goes on-chain, never personal data.

## 12. Deployment

- **Frontend:** Vercel, deployed automatically by **GitHub Actions** on push to `main`.
- **Backend:** FastAPI + PostgreSQL; currently runs on a dedicated machine exposed through a tunnel for demos (cloud hosting planned).
- **Live classes:** LiveKit Cloud.
- **Blockchain:** Polygon mainnet registry contract.

## 13. My role

I designed and built the platform end to end at CarbonRepro: the architecture, the database models, the FastAPI
modules, the AI layer (gateway, AI Teacher policy, course pipeline, notes, teacher AI), the three portals in
Next.js, payments in test mode, live classes, and the certificate system. I also review a teammate's frontend
pull requests and own deployments.

## 14. Roadmap

- Real payment gateway (JazzCash / Easypaisa / cards) and real refunds.
- Cloud hosting for the backend and the avatar engine.
- More subjects for the AI Teacher (Biology first, then Computer Science).
- Pre-rendered lesson videos for smoother avatar lip-sync.

---

<div align="center">

**Muhammad Yousaf Khan** · AI & Full-Stack Developer<br/>
**GitHub:** https://github.com/yousaf1145 · **LinkedIn:** https://linkedin.com/in/yousaf-khan-a560573b8

</div>
