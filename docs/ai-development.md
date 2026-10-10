# How I use AI to build Trial Folio

This page explains in plain terms how I, Nathan Slaughter, use AI to build Trial Folio. You don't need to know how software is built to follow it.

## The short version

- I use several AI tools to help write Trial Folio's plans, documentation, and code.
- I decide what Trial Folio should do, I check the work, and nothing becomes part of Trial Folio until I approve it.
- Trial Folio itself doesn't use AI when you run it.

## Who does what

**What I do:**

- Decide what Trial Folio should do, and write those requirements.
- Make every decision, and record it with its date.
- Review the drafts and say what to change.
- Approve the final version of every change.

**What the AI does:**

- Helps turn my requirements into a detailed written plan.
- Writes first drafts of code and documentation.
- Reviews each draft for mistakes before I see it.
- Revises the drafts based on my direction.
- Runs the automated checks and reports the results.

## How a change gets made

1. **I write down what's needed.** I describe in plain terms what the software should do.
2. **We turn it into a detailed plan.** The AI and I go back and forth on a written description, called a specification, of exactly how the software should behave, until I'm satisfied.
3. **The AI writes the code, an AI review checks it, then I review it.** The AI writes a first draft from the plan, and an AI review checks it for mistakes. The AI review's comments appear on the proposed change under my name. Then I review it and say what to change. The AI revises until the work matches the plan.
4. **I confirm the final version.**
5. **I accept it into the project.** Each change waits as a proposal until I approve it. Only then does it become part of Trial Folio.

## Safeguards

- **Automated checks.** Small test programs check that the software does what the plan says. They run before any code change leaves my computer, and again on GitHub for every proposed change, where anyone can see whether they passed. A change is merged only once they pass.
- **Portfolio123 credits.** Tests that contact Portfolio123 use real API credits. They run only when I approve them, with a set budget, and while I'm present.
- **Passwords and keys.** My Portfolio123 keys are kept in a password manager and supplied only to the commands that need them. They're never written into the project's files or logs.
- **The AI's instructions are public.** The exact instructions I give the AI are in [AGENTS.md](../AGENTS.md), which anyone can read. For example, they tell it never to say a test passed unless it actually ran it.

## AI inside Trial Folio

- The current versions of Trial Folio don't use AI at all. They contact only Portfolio123, and only for requests you approve.
- If optional AI features are added later, they'll be off unless you turn them on, and you'll be told before anything is sent to an AI service.

## Why the AI isn't listed as a co-author

- **I'm responsible for every change.** So each change is recorded under my name, and this page explains AI's role instead of a note on every change.
- **Using AI is now a normal part of writing software, and you should expect it.** Labeling each change as AI-assisted wouldn't tell you anything new.
- **I often use more than one AI tool on a single change.** Crediting any one tool or model would likely be inaccurate.

## Questions

If you have questions about how I build Trial Folio, see [CONTACT.md](../CONTACT.md).
