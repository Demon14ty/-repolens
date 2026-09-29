# Evaluating RepoLens

A small, honest evaluation for Version 1. It is not a benchmark.

## Repositories

`questions.json` lists five small public Python repositories, one per supported style:

| Repository | Style |
|---|---|
| miguelgrinberg/microblog | Flask (application factory) |
| streamlit/streamlit-example | Streamlit |
| fastapi/full-stack-fastapi-template | FastAPI (in a `backend/` folder) |
| wsvincent/lithium | Django |
| kennethreitz/records | Library with a CLI |

Each entry records the expected framework, expected entry point, and a few beginner questions with the files
that should answer them (`expected_sources`). Those files will also be used to evaluate source-cited Q&A in
Phase 2.

## Automatic checks

```bash
python -m evaluation.run_eval
```

This measures:

- **Framework detection accuracy**: detected framework == expected.
- **Entry-point accuracy**: top likely entry point == expected.
- **Citation coverage**: how many `expected_sources` appear in the learning path or code flow.
- **Response time**: GitHub download plus analysis, without the LLM.

The expected values were written by a person who read each repository. Some of them were checked after
RepoLens had already been run on those repositories, so treat a perfect score as a regression test, not as
proof of accuracy on repositories RepoLens has never seen. To measure that, add new repositories and write
their expectations before you run RepoLens on them.

## Manual checks (about 5 minutes per repository)

Score each from 1 (poor) to 3 (good):

- **Reading-path usefulness**: would a beginner understand the main flow after reading only these files, in
  this order?
- **Citation accuracy**: open each cited `path:line` range. Does it show what the text claims?
- **Challenge quality**: is the quest small (under an hour), grounded in real files, and clearly testable?
- **AI explanations** (if an API key is configured): are they faithful to the evidence? Were any passages
  dropped by the citation check, and was that correct?

Record results in a table next to the RepoLens version so you can see regressions over time.
