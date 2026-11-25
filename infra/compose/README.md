# infra/compose

`docker-compose.yml` with the `core`, `lake`, `platform`, `obs` and `all` profiles, and `.env.example` (ports, dummy credentials, placeholder for the LLM key).

```bash
cp infra/compose/.env.example infra/compose/.env   # once; adjust ports if they are taken
make up PROFILE=core                               # start and wait until healthy
make ps                                            # status and health
make test-integration                              # checks against the running stack
make down                                          # stop, keeping the data
```

Operations and troubleshooting: [docs/runbooks/local-environment.md](../../docs/runbooks/local-environment.md).
