# Kaggle ISLR 250-sign vocabulary vs. demo needs

Source: `sign_to_prediction_index_map.json` from the [1st-place model on Hugging Face](https://huggingface.co/sign/kaggle-asl-signs-1st-place) (also has a ready `model.tflite`, 11.2 MB, MIT). The sections after "Draft demo script" were a first-pass guess from the design doc's demo plan.

## Draft demo script
**Oct 24: the project is Meet only.** Only the Meet line below still matters; the Claude Code and Siri lines are kept for the record. The ASL Citizen model (2,731 signs) is being added for the signs the Kaggle 250 lacks.

From `asl-demo-script-research.md`, which links a source for every sign. These are drafts: a Deaf signer must approve them before the demo.
- Claude Code kick-off: `FOOD STORE /\ WW MAKE`, then `YES`. In vocab: food, store, make, yes. Custom: WW.
- Siri: `TOMORROW MORNING, you-REMIND-me BUY MILK`. In vocab: tomorrow, morning, milk. Custom: REMIND, BUY.
- Meet: `HELLO, NICE MEET-you` / `HOW YOU?` / `FINE` / `THANK-YOU`. In vocab: hello, fine, thankyou. Custom: NICE (or map `clean`, the same sign), MEET, HOW, YOU.
- Re-prompt: `TITLE /\ RED`. In vocab: red. Custom: TITLE.
- Weather fallback: `TOMORROW RAIN` with raised brows (a question). In vocab: tomorrow, rain.
- Custom signs to train: WW, REMIND, BUY, MEET, NICE (or map CLEAN), HOW, YOU, TITLE.

## Claude Code build + live edit
- In vocab: make, red, blue, black, white, yes, no, finish, now
- Missing: website, build, page, title, big, bigger, small, change, color

## Siri weather
- In vocab: rain, snow, sun, cloud, hot, tomorrow, now
- Missing: what, weather, cold, today

## Siri music
- In vocab: radio, listen, loud, quiet
- Missing: play, music, song, stop

## Siri reminder (chosen for the demo)
- Demo gloss (draft): `TOMORROW MORNING, you-REMIND-me BUY MILK` → "Remind me tomorrow morning to buy milk." REMIND is a real sign, not fingerspelled.
- In vocab: time, later, tomorrow, morning, night, callonphone, store, milk
- Missing: remind, buy, call

## Meet call
- In vocab: hello, bye, thankyou, yes, no, minemy, fine, bad, haveto, wait, please, where, who, why
- Missing: how, you, me, good, name, nice, meet, understand, again, sorry, help, want, need

## Full vocabulary (250)
TV, after, airplane, all, alligator, animal, another, any, apple, arm, aunt, awake, backyard, bad, balloon, bath, because, bed, bedroom, bee, before, beside, better, bird, black, blow, blue, boat, book, boy, brother, brown, bug, bye, callonphone, can, car, carrot, cat, cereal, chair, cheek, child, chin, chocolate, clean, close, closet, cloud, clown, cow, cowboy, cry, cut, cute, dad, dance, dirty, dog, doll, donkey, down, drawer, drink, drop, dry, dryer, duck, ear, elephant, empty, every, eye, face, fall, farm, fast, feet, find, fine, finger, finish, fireman, first, fish, flag, flower, food, for, frenchfries, frog, garbage, gift, giraffe, girl, give, glasswindow, go, goose, grandma, grandpa, grass, green, gum, hair, happy, hat, hate, have, haveto, head, hear, helicopter, hello, hen, hesheit, hide, high, home, horse, hot, hungry, icecream, if, into, jacket, jeans, jump, kiss, kitty, lamp, later, like, lion, lips, listen, look, loud, mad, make, man, many, milk, minemy, mitten, mom, moon, morning, mouse, mouth, nap, napkin, night, no, noisy, nose, not, now, nuts, old, on, open, orange, outside, owie, owl, pajamas, pen, pencil, penny, person, pig, pizza, please, police, pool, potty, pretend, pretty, puppy, puzzle, quiet, radio, rain, read, red, refrigerator, ride, room, sad, same, say, scissors, see, shhh, shirt, shoe, shower, sick, sleep, sleepy, smile, snack, snow, stairs, stay, sticky, store, story, stuck, sun, table, talk, taste, thankyou, that, there, think, thirsty, tiger, time, tomorrow, tongue, tooth, toothbrush, touch, toy, tree, uncle, underwear, up, vacuum, wait, wake, water, wet, weus, where, white, who, why, will, wolf, yellow, yes, yesterday, yourself, yucky, zebra, zipper