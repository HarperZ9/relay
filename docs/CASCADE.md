# Local-first cascade

Some questions in an agent loop do not need a model. "Is this test failure flaky, or did the code break it?" can often be answered from the failure text alone. The cascade asks a local classifier first and sends the question to your model endpoint only when the classifier abstains. Every answer is written to the session ledger with who answered it, so you can see how many endpoint calls the cascade saved and check each local answer afterwards.

## Bar, set before the run

This bar was committed before the classifier was written and before its author read any labelled failure.

**Labels.** 160 failure tails from pytest, unittest, jest, go test, cargo and JUnit, each labelled flaky or real by a separate labeller who saw no code (`tests/fixtures/flaky_failure_labels.json`). About a quarter are marked hard on purpose. Items are split in half by a seeded hash of their id.

**Threshold.** Chosen on the dev half only: the lowest confidence threshold at which the classifier's accuracy on the items it decides is at least 0.95.

- **C1, endpoint calls.** The classifier decides at least 50% of test items, so the endpoint sees at most half the questions it would see without the cascade.
- **C2, local accuracy.** Accuracy on the test items the classifier decides is at least 0.95.
- **Control.** With the labels shuffled, C2 must fail.
- **Ship rule.** The cascade ships opt-in whatever the result, with the numbers below.

**What this does not measure.** The sprint plan named a paired run of 30 agent tasks with and without the cascade. That run needs a model endpoint for every task and was not done here. C1 and C2 bound the effect instead: escalated questions reach the endpoint exactly as before, so task success can only fall on questions the classifier decides, and only where it is less accurate than the endpoint would have been.

## Results

Pending the run.
