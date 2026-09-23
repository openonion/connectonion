# A Wiki preview is not the Wiki release

The first Wiki preview could build maps and produce a project page. It also passed thousands of offline checks. Then a real first-run investigation tried three people and wrote none of their pages. The default model was unavailable for the account, the mailboxes used by initialization were not gathered for investigation, and the validator rejected pages whose evidence the model found through other commands. These observations are recorded in [issue #1628](https://github.com/openonion/connectonion/issues/1628).

That failure changed what the version number should promise. `1.8.8b1` remains an installable, immutable preview of the work we had. The Personal Wiki feature now targets `1.9.0`, with the real-person failure as a release blocker. Changing the target is planning, not a rewrite of what shipped or a claim that every associated design proposal must be complete in one build.

The acceptance unit is a user's actual path: initialize a notebook, see what sources were covered, choose a real page, investigate it, inspect the evidence, correct a mistake, and read or share the updated result. A model's polished draft and a validator's pass are useful intermediate signals. Neither by itself says that the page reached the notebook or that its claims are supported.

The [1.9.0 release plan](/cli/wiki-190-release-plan.md) names the blocking failures and separates them from longer-term exploration. The next useful proof is to rerun the failing people cases against a reviewed build and retain the pages, coverage, usage, and rejection reasons. Until that proof exists, the preview label should stay visible.
