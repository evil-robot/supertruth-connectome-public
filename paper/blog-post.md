---
slug: fruit-fly-brain-beat-four-ai-models-at-judging-health-records
title: A fruit fly's brain beat Claude, GPT-5, Grok and Gemini at judging health records
category: news
author: Jason Alan Snyder
cover: https://supertruth.ai/research/connectome/fig1.png
cover_attribution: SuperTruth, drawn from MaleCNS v1.0 (HHMI Janelia and partners, CC BY 4.0)|https://male-cns.janelia.org/
excerpt: This is not a stunt with a fly. It is a test of what intelligence is made of, and what happens when you hand any kind of intelligence bad data. We ran medical records through a fruit fly's brain and through four big AI models. Nature won. Here is why that matters for anyone whose health depends on a record being right.
meta: A fruit fly's fixed brain wiring matched SuperTruth's health data trust score 84 times out of 100. Four big AI models managed 20 to 45. Why nature won, and why data is what matters.
published_at: 2026-09-21
---

Let me get one thing out of the way first. This is not a stunt.

Yes, we ran medical records through a fruit fly's brain. Yes, it beat four of the biggest AI models in the world at the job. That is a fun headline, and it is true. But it is not the point. The point is what the test says about intelligence, about nature, and about data. Especially health data. Especially getting it right.

## What we did

In June, scientists at Janelia, Cambridge, the MRC lab in England and Google finished a map of a fruit fly's entire central nervous system. Every nerve cell. Every connection between them. 166,700 cells and a little over six million connections, photographed slice by slice under an electron microscope. They gave it to the world for free.

We took that map exactly as it was. We did not add a connection. We did not move one. The only thing we let change was how loudly each connection spoke, like a volume knob. Then we trained it to copy the number our software gives a medical record. That number is the Data Trust Index. It runs from 0 to 100 and says how far you can trust the record.

We built 20,000 medical records for the test. No real patient was anywhere near it.

Then we gave the same job to Claude Opus 5, GPT-5, Grok 4 and Gemini 3 Flash. Each one got our published paper explaining how the score works, plus 300 of the same records. Each ran three times.

## What happened

The fly's brain picked the right trust level 84 times out of 100.

The four models picked it 20, 29, 28 and 45 times out of 100.

Ask the fly twice, you get the same answer twice. Not one of the four models could do that.

To be fair to them, this measured how closely each one matched our score, not who was right about the records. And the fly was trained on the answers while the models only read about the method. So we ran a second round and gave the models 100 scored examples to learn from. That changed things. GPT-5 and Grok 4 roughly doubled, to about 54 and 55 out of 100. Gemini 3 Flash went from 45 to 63. Claude Opus 5 jumped from 20 to 76, eight points behind the fly, and gave the same answer twice on only 3 records in 100. Examples help a lot. The fly still wins all four, and it still costs nothing per record and never changes its mind.

## What intelligence is made of

Here is the part that matters.

We scrambled the fly's wiring and ran the test again. Same number of connections per cell, same pushes and pulls, but who connects to whom was shuffled at random. The scrambled brain did just as well as the real one. Then we tried a purely random web of connections the same size. It did just as well too. And an ordinary trained network with the same number of adjustable parts did worse than all three.

So it was never about the fly. It was about the shape of the thing. A fixed, thin web where every connection pushes or pulls and nothing gets rewired while it learns. That shape did the work. Not size. Not billions of parameters. Not more data scraped from the internet. Structure.

Nature figured this out a very long time ago. A fruit fly runs on about a millionth of the energy of a data center and never asks the same question twice. Evolution did not get there by making the brain bigger. It got there by making the structure right. I have said for years that the future of intelligence is biological and quantum, and that we have far more to learn from nature than we have learned so far. In fact, everything. This is one small piece of evidence.

## Why data is the whole game

Now the part I actually lose sleep over.

The big models are what my friend John Kheit calls kerplinko machines. Drop a token in the top, let it rattle down through billions of pins, see where it lands. The pins were placed by the internet, which rewards what spreads over what is true. The machine inherits that at the root.

Any intelligence, a fly's or a model's or yours, is only as good as what you feed it. Feed it a wrong record and it will give you a confident wrong answer. That is not a bug in the model. It is the data.

In health, that is not an abstract worry. A record says a patient is not allergic to a drug. A record says a lab result is from this year when it is from three years ago. A record says a person lives at an address they left. Someone acts on it. A real person pays.

That is why SuperTruth exists. Not to build a bigger brain. To make sure the data any brain acts on is right, and to prove it, so trust is something you can check instead of something a vendor tells you.

## What we got wrong

We wrote the rules before the first run and promised to publish either way. The fly passed three of our five bars. It missed our target for getting the trust level right (88 percent on the full test set, against a bar of 90), and it missed on the part of the score that tracks how recent a record is. We say so in the paper. This is the first of five runs. The numbers may move, and when they do the paper gets a new version at the same address.

## Check it yourself

Everything that does not give away our own inventions is released. The 20,000 records, the score for each one, and the trained fly model are free to download. The rules, the code, and every call to every model with its price are in the paper. If you want to know about what we held back, ask. We will work with you.

The paper: [Intelligence Is Structure, Not Scale](https://doi.org/10.5281/zenodo.22865214).
The data: [doi.org/10.5281/zenodo.22865020](https://doi.org/10.5281/zenodo.22865020).
The page, with a 3D view of the brain: [supertruth.ai/research/connectome](https://supertruth.ai/research/connectome).

Simply put, the future of intelligence is analog. And data is what decides whether it helps you or hurts you.
