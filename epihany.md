## Your idea, restated

Any non-trivial problem, like comparing research papers, can be solved along many different **solution paths**: different sequences of steps, with different intermediate representations between them. The set of all reasonable options is called the **design space**.

Every step in every path is also a fork. You can solve it **deterministically**, with explicit rules, parsers and arithmetic, where the same input always gives the same output. That's classical programming, sometimes called "Software 1.0". Or you can solve it **probabilistically** with an LLM, which is fuzzy: it copes with messy, ambiguous input, but its output can vary and is sometimes wrong. So each path involves two layers of decisions: the shape of the path, and the kind of tool at each step.

**Before AI**, engineering time was the scarce resource. Writing the parser, the rules and the classifier was laborious, so teams debated on a whiteboard, picked one path early (a "big design up front" approach) and lived with it. Two well-known traps followed:

- **Path dependence:** early choices lock in later ones.
- **Sunk-cost fallacy:** "we've already built this, so we keep going."

It's like an architect who can only afford to build one house and must commit from the blueprints alone.

**With AI**, two things changed at once. AI coding assistants collapsed the cost of writing code, and LLMs became a new kind of building block for the steps themselves. Exploring several paths is now cheap. You can run time-boxed experiments (**spikes**, in agile terms) and hold a **bake-off**, which turns design from a debate into an empirical question: build several, measure, pick. The "LLM or classical?" question also becomes a per-step experiment, where you swap one component and see what changes (an **ablation**).

**The bottleneck moves** from generating solutions to judging them. Many cheap paths are only useful with a fair yardstick, meaning a hand-labelled gold set, agreed metrics and automated **evals**. Without those, you have eight prototypes and eight opinions. The durable asset becomes the evaluation harness, and the paths themselves become disposable.

There's also a nice irony. The champion vs challenger framework you're applying to the papers now applies to the solution paths as well.

## Jargon used, in plain English

| Term                           | Plain meaning                                                |
| ------------------------------ | ------------------------------------------------------------ |
| **Design space**               | Every reasonable way you could build the thing               |
| **Solution path**              | One complete design: the steps, their order, and what's passed between them |
| **Pipeline**                   | A solution path once it's implemented as running stages      |
| **Deterministic**              | Same input, same output, every time                          |
| **Probabilistic (stochastic)** | Output can vary between runs and is a best guess             |
| **Path dependence**            | Early choices constrain later ones                           |
| **Sunk-cost fallacy**          | Continuing because of what's already been spent, not what's best |
| **Spike**                      | A short, throwaway experiment to answer a design question    |
| **Bake-off**                   | Running several candidates on the same task and comparing results |
| **Ablation**                   | Swapping or removing one component to see what it contributes |
| **Evals / gold set**           | Automated tests scored against hand-labelled correct answers |
| **Champion-challenger**        | Comparing a new candidate against the current best on the same yardstick |

I can also compress this into a single paragraph if you want something short to share.
