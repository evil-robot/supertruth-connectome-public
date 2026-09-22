# SuperTruth company page article (sharpened from Rheanna's 21 Sep draft)

Production notes: cover media = fly wiring video (fly_wiring_rotation_1080p.mp4); Chart 1 after "What happened"; Chart 2 after "The finding". Headline options below avoid "beat" per Rheanna; JAS picks.

Headline options
A. A Fruit Fly's Brain Matched Our Health Data Trust Score. Four Leading AI Models Could Not.  (recommended)
B. Structure, Not Scale: What a Fruit Fly's Wiring Taught Us About Trusting Health Data
C. We Gave a Fruit Fly's Brain and Four AI Models the Same Medical Records. Here Is What Happened.

---

## A Fruit Fly's Brain Matched Our Health Data Trust Score. Four Leading AI Models Could Not.

SuperTruth's software reads a medical record and scores how far it can be trusted, 0 to 100. We call that score the Data Trust Index, or DTI. This weekend we handed that job to a fruit fly's brain.

Not a live fly. A map of one. In June, scientists at HHMI Janelia, the University of Cambridge, the MRC Laboratory of Molecular Biology and Google Research finished mapping a fruit fly's entire central nervous system: every nerve cell and every connection between them, photographed slice by slice under an electron microscope and released for anyone to use (https://male-cns.janelia.org/). 166,700 nerve cells. 6,242,118 connections. Those scientists had no part in what we did next and have not endorsed it.

We took the map exactly as it was. We did not add a connection or move one. We only adjusted how strongly each existing connection spoke, like turning a volume knob. Then we trained that wiring to reproduce DTI scores on records we built for the test. No real patient's data touched any of it.

Then we gave the same job to four AI models people know by name: Claude Opus 5, GPT-5, Grok 4 and Gemini 3 Flash. Each got our published methodology and 300 of the same test records, cold, with no examples to learn from.

## What happened

The fly's wiring matched our trust score on 84 records out of 100. The four models: 20 to 45. Ask the fly twice and you get the same answer both times. None of the four models came close to that.

[Chart 1: The fly beat all four models, with or without help]

## Is that a fair fight?

No, and we want to say so before anyone else does. The fly's wiring was trained on thousands of records our own software had already scored. The four models only read a paper describing how the score works. A system trained on the answer key will track the answer key better than one that read the textbook. That is not the finding.

So we ran the fairer version too. Each model got 100 of our scored examples to study first. They improved a lot, climbing to 54 to 76 out of 100. The fly held at 84, answered in 16 thousandths of a second, and gave the same answer every time. The most consistent model repeated its own answer word for word less than a third of the time.

## The finding

We scrambled the fly's wiring so no connection sat where it does in a real fly. It did just as well. We built a random web of connections from scratch, the same size. It did nearly as well. An ordinary trained network with the same number of adjustable parts did worse than all three.

The fly's particular brain was never the secret. The secret is the shape: a fixed, thin structure where every connection either pushes or pulls, and nothing gets rewired while it works. Structure did the work. Not scale.

[Chart 2: The fly's exact wiring did not matter. The kind of wiring did.]

We are not saying a fly is smarter than a chatbot, and we are not treating patients with this. We are saying structure did more work than scale, in a test built to make that visible.

"When a hospital acts on a bad record, a real person pays for it. That is who this is for. People have been told that bigger AI means smarter AI, and that a confident answer is a correct answer. Neither is true. What decides whether AI helps a patient or hurts one is the data it was handed and whether anyone checked it. A fruit fly's brain just showed how much that matters." Bobby Hill, Co-Founder and Chief Executive Officer, SuperTruth

## How we ran it

We wrote the rules and the controls before the first run and promised to publish whichever way it came out. The fly passed three of the five bars we set for it and missed two. Two of five planned runs are complete; the rest are under way, and the paper is updated at the same address as they land. A wiring that fails is a fact worth having too.

Everything that does not expose our own inventions is released: all 20,000 records, every score, the trained fly model and the full paper. A plain-language summary with a 3D view of the wiring is at supertruth.ai/research/connectome. If you think we left something out, ask. We will work with you.

We name Claude, GPT-5, Grok and Gemini so you can see what we tested. The test measured how closely each system matched SuperTruth's own score, not who was right about the records, and it ranks no vendor. None of those companies is affiliated with SuperTruth, and none has reviewed or endorsed this work.

SuperTruth proves health data can be trusted before an AI model acts on it. Data truth is AI truth.

## Links

The paper: https://doi.org/10.5281/zenodo.22865214
The data, every record and every score: https://doi.org/10.5281/zenodo.22865020
The page, with a 3D view of the wiring: https://supertruth.ai/research/connectome
The story, by our co-founder: https://supertruth.ai/blog/fruit-fly-brain-beat-four-ai-models-at-judging-health-records
