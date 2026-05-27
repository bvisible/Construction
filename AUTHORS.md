# Authors

OpenConstructionERP is created and maintained by **Artem Boiko**, founder of
[DataDrivenConstruction](https://datadrivenconstruction.io) — author of the CWICR
cost database (55,000+ items, 24 languages), with 10+ years in construction cost
estimation.

## Maintainer

- **Artem Boiko** — founder & lead maintainer ([@boikoartem](https://github.com/boikoartem))

## Contributors

OpenConstructionERP is built together with the community.

- **skolodi** ([@skolodi](https://github.com/skolodi)) — issue reports and
  field feedback on the BOQ AI assistant.
- **Mourtadha Diop** ([@Mourdi59](https://github.com/Mourdi59)) — fixed three
  BIM viewer bugs ([#159](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/159)):
  COLLADA namespace-prefix serialisation in `ifc_processor`, defence-in-depth
  regex tolerance in `ElementManager`, and `degraded` model status surfacing
  in the viewer UI.
- **rjohny** ([@rjohny55](https://github.com/rjohny55)) — multi-area patch set
  ([#161](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/161)):
  defensive guards for the slow-query SQLAlchemy listener and module-presence
  probe under concurrency, FieldReport activity-rollup column fix, Qdrant
  multipart snapshot upload (so app-container snapshots reach a separate
  Qdrant container), and three new AI providers — Kimi (Moonshot AI),
  Ollama, vLLM — with custom base URL support for the two local backends.

See the full list of everyone who has contributed:

https://github.com/datadrivenconstruction/OpenConstructionERP/graphs/contributors

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
