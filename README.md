# PromQL Witness

Two expressions can draw the same graph today and disagree the moment one pod restarts. This tiny benchmark grades a proposed PromQL expression against **two different histories for the same task**. Prometheus itself runs the queries.

## Run the demo

Requires Python 3.9+ and `promtool` from the [Prometheus release](https://prometheus.io/download/). Put the executable on your PATH or set `PROMTOOL` to its full path. No Python packages, running server, GPU, cluster, or account are required for the bundled demo.

```sh
python3 demo.py
```

| Task | Input history | Reference | Plausible alternative |
|---|---|---:|---:|
| Current service throughput | Both pods running | 5 req/s | 5 req/s |
| Current service throughput | One counter reset | 5 req/s | 2 req/s |
| Service-wide error percentage | Equal traffic on both pods | 25.5% | 25.5% |
| Service-wide error percentage | Pod A gets 9× the traffic of B | 5.9% | 25.5% |

All four rows are tested on invocation. Expected values come from the input traffic, and both expressions are executed. Each expected result is a single unlabeled sample. Fixtures and PromQL expressions are defined in `demo.py`. The sample interval is 1 minute and evaluation takes place at minute 4.

In the reset case, pod A counts 180 → 60 and pod B counts 720 → 960. The per-pod increases add up to 300 requests in 60 seconds. Aggregating first hides the reset and leaves an apparent increase of only 120. In the error case, the pods have 1% and 50% errors. With request rates of 900 and 100 per second, the service sees 59 errors per 1,000 requests.

## Test a model answer

Print just the task and give it to the model in a fresh session. The task contains the metric description but withholds the fixtures, reference and alternative. Paste the model's query between single quotes.

```sh
python3 demo.py --prompt restart
python3 demo.py --case restart --query 'sum(irate(http_requests_total[2m]))'
python3 demo.py --case restart --query 'irate((sum(http_requests_total))[2m:1m])'
```

The second command succeeds. The third exits with status 1 and prints the expected and observed numbers. The other case is called `errors`.

### Optional API run

Use a Chat Completions-compatible endpoint you already use. Set `LLM_BASE_URL` to its base URL including `/v1` and `LLM_MODEL` to a model it serves. If your provider requires authentication, supply `LLM_API_KEY` in the environment. A run sends one synthetic task to the supplied endpoint and may incur a provider charge.

```sh
python3 run_model.py errors --base-url "$LLM_BASE_URL" --model "$LLM_MODEL" --out trial-01.json
```

This saves the exact prompt, raw reply, model ID, timestamp and usage (where returned), then grades the expression locally. Use a new file and a fresh request for each trial. A previously collected answer can be graded offline with `demo.py --query`.

## What these numbers mean

The bundled alternative queries were written by hand. The four rows establish that the fixtures can distinguish the two expressions. They do not establish how often a model makes either mistake. A query can pass both small fixtures and still fail on other data.

For a first report, collect one answer per independent trial without showing fixtures to the model. Report how many queries passed the ordinary history but failed the changed history, divided by the number that passed the ordinary history. List syntax errors and failures on both histories separately. Publish the prompts, model IDs, raw answers, versions and counts. Include additional unseen fixtures before drawing model-level conclusions.

Related work: [Grafana o11y-bench](https://github.com/grafana/o11y-bench), [PromCopilot](https://github.com/FudanSELab/PromCopilot), [five executable counter-reset cases](https://dreamtsoft.com/blog/prometheus-counter-reset-aggregation/), and the [Prometheus rule testing format](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/).

## License

MIT. See the repository LICENSE.
