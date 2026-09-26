# mouse-pointing-tsc

Classifying pointing target size from mouse cursor speed time series. Final assignment for Time Series Mining, PUCPR.

## Task

Each example is one mouse movement from the screen center to a target 300 px away, in a random direction. The class is the target diameter:

| Class | Diameter | WCAG 2.2 reference |
| -------- | -------- | ---------------------- |
| `small` | 12 px | below the minimum |
| `medium` | 24 px | minimum (AA) |
| `large` | 44 px | enhanced (AAA) |

## Data

180 movements from one participant, collected with [01_collect_sessions.py](01_collect_sessions.py) in 6 sessions on 25-26 September 2026. Same mouse, monitor and pointer settings throughout.

| Split | Sessions | Per class | Total |
| ----- | -------- | --------- | ----- |
| train | 1, 3, 5 | 30 | 90 |
| test | 2, 4, 6 | 30 | 90 |

```
data/
  raw/session_XX/   collector output, one folder per session
  train/<class>/    one CSV per movement
  test/<class>/     one CSV per movement
  trials.csv        metadata of all movements
```

Series columns: `t` (seconds since target onset), `x`, `y` (pixels).

## Reproduce

- Notebook: Colab link coming soon
- Rebuild train/test from raw: `python 02_build_dataset.py`
- Collect a session: `python 01_collect_sessions.py --session N`
