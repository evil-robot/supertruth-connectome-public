# Everyone is arguing about models. The argument is about data.

Two days ago [a fruit fly's brain](https://huggingface.co/mlabonne/chessfly) [made the news](https://nypost.com/2026/09/19/us-news/fruit-fly-beats-claude-opus-5-at-chess/) for beating a large AI model at chess. I read that and thought: chess is a game. Give it a job that matters.

So we did. We took the complete wiring map of a fruit fly's nervous system. 166,700 nerve cells and 6,242,118 connections. Scientists at Janelia, Cambridge, the MRC and Google mapped it slice by slice under an electron microscope and released it to the world in June. We did not move a single connection. We changed only how loudly each one spoke, and we asked that wiring to copy the score our software gives a medical record: can this record be trusted, 0 to 100.

Then we gave the same job to Claude Opus 5, GPT-5, Grok 4 and Gemini 3 Flash.

On the same 300 records, the fly picked the right trust level 84 times out of 100. The four models picked it 20, 29, 28 and 45 times. We gave them a second round with 100 scored examples to learn from, and they improved a lot: Claude reached 76, Gemini 63, Grok 55, GPT-5 54. The fly still led. It answered in 16 thousandths of a second, on a laptop, for nothing per record, and it gave the same answer every time it was asked. Not one of the four models managed that. We measured that more than one way. By the strictest measure, the exact same output all three times, Claude at its best gave the identical answer on only 3 records in 100. It also cost 43 cents a record.

Then came the part that surprised us. We scrambled the fly's wiring and ran the test again. It did just as well. A purely random web of connections the same size did just as well too. And an ordinary trained network with the same number of adjustable parts did worse than all three. So it was never about the fly. It was about the shape of the thing: a fixed, thin web (a sparse, signed graph) where every connection either pushes or pulls, and nothing gets rewired while it learns. The paper calls it the substrate, not the anatomy. Structure did the work. Not size.

We wrote the rules before the first run (pre-registered them) and promised to publish no matter how it came out. The fly passed three of the five bars we set for it and missed two. The paper says so. All five planned runs are done, and the finding held. Every record, every score and the trained model are free to download, so anyone can check any number. Links are at the bottom.

But this article is not about the fly. The fly is a doorway. I want to talk about what is on the other side of it.

## The conversation we keep having

Every week there is a new model. Bigger. More parameters. A new benchmark beaten. And every week the conversation is the same: which model is smartest, which one is winning, which one should you bet your company on.

I think it is the wrong conversation, and I think a fruit fly just showed why.

Large language models are hideously inefficient. To do what they do, they need to do the same thing over and over and over again. That is why they burn so much power. That is why they have to be so huge.

And think about what they are doing it to. For us, spoken language is tied up with breath. Now we have a machine that never needs to breathe, reading and judging words that came from people with bodies (embodied practice). The models do not have emotions. Humans do. Living things have spent millions of years learning to compute cheaply (analog computation, energy-efficient by necessity), because an animal that wastes energy dies. A fly runs on a crumb. Nature has a lot to teach us about how to do that. In fact, I think it has everything to teach us.

We handed one of nature's designs a job it had never seen, and it did the job, cheaply, the same way every time. The lesson is not that flies are smart. The lesson is that we have been measuring the wrong thing. We have been measuring size. We should have been measuring structure. And we should have been asking a harder question: what are we feeding it?

## Kerplinko machines

My friend and mentor John Kheit has a name for large language models. Kerplinko machines, after pachinko. Drop a token in at the top, let it rattle down through billions of pins, see where it lands.

Who placed the pins? The internet. The model learned from what people posted, and the internet rewards what spreads, not what is true. So the machine starts life with that bias built in, at the very bottom (at the kernel, as an engineer would say), before it answers a single question. It learned popularity and called it truth. Making the model bigger does not fix that. A bigger model learns the same bias in more detail.

Choosing what goes in is part of making the thing. Curation is part of creation. What you feed a mind at the start (its boot sequence) shapes everything it does after. Very few people building these systems are bothering with that. We are.

The fly's brain was built by a world that does not care what is popular. Every connection in it is a fact you can look up in a public dataset, with the type of cell and the chemical it uses (its neurotransmitter). You can open it. You can check it. That is why I call it a different kind of judge. Not a smarter one. A checkable one.

## What trust actually means

Here is what I have learned building a company that scores whether health data can be trusted.

Trust is not a feeling and it is not a brand. It is something you can check. A record you can trust has a source you can name and a date you can confirm. It has a path you can follow from where it started to where it is now (a chain of custody). And it has consent you can point to. If you cannot check those things, you do not have trust. You have deference. You are taking someone's word for it.

Most AI today runs on deference. A model gives you a confident answer. You cannot see where it came from, whose data it was, or whether it was true the day it was used. The big assumption in health AI is that a model's judgment can be trusted because the company selling it (the vendor) says so. That is not trust. It is deference. Trust has to stop being a vendor's claim and become something you can check (a property you can audit).

## Consent is not paperwork

Now the word nobody in the model race wants to say: consent.

Whose data trained the model? Did they agree? Do they even know? In most cases the honest answer is no, no, and no. That is not a footnote. In health it is the whole thing. A patient's record is the most private document a person has. Using it without permission is not a paperwork problem. It is a betrayal.

We ran this entire study on 20,000 records we built for the purpose. No real patient anywhere near it. Not because a rule made us. Because the study is about trust, and you cannot make a point about trust on stolen ground. Consent is one of the eight parts (dimensions) of our trust score for exactly this reason. A record can be perfectly accurate and still be something you had no right to use.

## Data decides

Put it together and the picture is simple. Any intelligence, a fly's or a model's or yours, is only as good as what you feed it. Hand it a wrong record and you get a confident wrong answer. Hand it a record you had no right to and you have built something on a lie. Scale fixes neither.

In health this is not abstract. A record says a patient has no allergy when she does. A lab value is three years old and looks like today's. An address is one the person left. Somebody acts on it. A real person pays.

So when the industry asks which model will win, the question is upside down. The model is the easy part. The hard part is the data. Is it right? Did the people it came from agree? Can anyone prove both? That is what decides whether AI helps a patient or hurts one. That is not glamorous. It is the entire game.

## What I believe

I have been saying for years that the future of intelligence is biological and quantum. We have far more to learn from nature than we have learned so far. Nature's designs deserve more respect than we give them. A fruit fly's nervous system just copied a trust score that four of the largest models on earth could not match. Then it told us the secret was structure, not size.

We should be careful what we hand control to. We should stop measuring intelligence by the size of the machine. We should treat what we feed a mind as part of making it. And we should start treating data the way we treat anything else a life depends on: check the source, confirm the consent, prove it, or do not use it.

The future of digital technologies is analog. Simply put, the future of intelligence is analog. And data truth is AI truth.

The paper: https://doi.org/10.5281/zenodo.22865214
The data, every record and every score: https://doi.org/10.5281/zenodo.22865020
The page, with a 3D view of the wiring: https://supertruth.ai/research/connectome
The plain-English story: https://supertruth.ai/blog/fruit-fly-brain-beat-four-ai-models-at-judging-health-records

The wiring is MaleCNS v1.0, released under CC BY 4.0 by HHMI Janelia Research Campus with the University of Cambridge, the MRC Laboratory of Molecular Biology and Google Research, who did not take part in this study and have not endorsed it. The four models were called through their makers' own services on 20 September 2026 with identical prompts. Each name is the property of its owner. The test measured how closely each system matched SuperTruth's own score, not who was right about the records, and it ranks no vendor. Two of five planned runs are complete. The numbers may move, and the paper will be updated at the same address when they do. We publish either way.
