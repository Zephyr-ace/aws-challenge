# Data Center Site Cost Estimation — Multi-Agent System

Four specialized agents estimate the costs of building and operating a data center at a given location, powered by OpenAI's Agents SDK with GPT-5.4 mini and web search.

## Agents

| Agent | Input | Output |
|---|---|---|
| Land Cost | coordinates, total_area | `land_cost` (total €) |
| Infrastructure | coordinates, total_area | `infrastructure_cost` (total €) |
| Power Supply | coordinates, total_area | `power_cost` (annual €) |
| Cooling | coordinates, total_area | `cooling_cost` (annual €) |

## Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
python main.py --lat 52.52 --lon 13.405 --area 5000
```
