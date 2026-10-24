# What Deaf users told us

We're a hearing team, so we asked Deaf ASL faculty at the University of Washington what they need before deciding what to build. This file keeps their answers word for word, and what we changed because of them.

## Professor Lance Forshay (UW, Deaf ASL faculty)

Survey response, Oct 23, 2026. He agreed to be quoted.

| Question | His answer |
|---|---|
| How do you use AI tools or smart assistants today? | "I only use AI google for summary of internet search." |
| How do you handle video calls with people who don't sign? What's most frustrating? | "I use Video Relay Service a lot with hearing people. Most frustrating is the quality of interpreter, hearing people hanging up the phone without understanding who it's from." |
| Would you use a tool that lets you sign to your webcam to control voice assistants, AI tools, and video calls? | Maybe |
| Which uses would matter most to you? | Video calls only |
| What would make you not trust or not use a tool like this? | "accuracy, government recording, privacy." |
| Have you tried other sign language technology? | "No" |
| What do you wish hearing developers understood when building tools for Deaf signers? | "Include and recognize Deaf researchers on YOUR team. Invest in the Deaf community not only with technology but economy as well." |

## What we changed

1. **Video calls are the centerpiece.** The Meet call gets the most time and polish in the demo. We open with a signed Claude Code request so it can build in the background, and Siri shows the same pipeline reaching other voice-first tools.
2. **Every call starts by saying who's calling.** Hearing people hang up on relay calls because they don't know who it is. In Meet mode the app introduces the signer in their Cartesia voice, and says "one moment, I'm signing" during long pauses so the other side doesn't assume the line is dead.
3. **Video never leaves the laptop.** Tracking and sign recognition run on the device. Only the recognized sign words go to Claude, as text, and only the final English goes to Cartesia. Nothing is recorded or saved, and the app always shows whether the camera is on.
4. **The signer sees the English before anyone hears it.** Claude Code already waits for a signed YES. Meet mode can do the same ("review before speaking"), so a misrecognized sign isn't spoken in the signer's name.
5. **We don't claim to replace interpreters.** This gives signers a direct option for short calls and voice-only tools. It's not a substitute for a qualified interpreter.
6. **Deaf people shape the next step.** After Cal Hacks we'll test with Professor Forshay in person (with an interpreter) and credit the Deaf people who guide the project by name.
