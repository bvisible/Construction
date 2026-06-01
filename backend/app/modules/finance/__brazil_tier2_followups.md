# Brazil Tier-2 Followups — SEFAZ NF-e, ICMS engine, SINAPI importer

Filed 2026-05-27 in response to feedback from JOAO VICTOR VIEIRA ESPOSITO
(OuroImoveisMn, luringlool@gmail.com, app_version 5.2.5):

> "there is no invoice support for brl"

Tier-1 (shipped in the same PR — see commit) closed the immediate gap:

- BRL added to FinancePage common-currency shortlist
- BR_SAOPAULO CWICR catalogue defaults to `sinapi` classification
- BOQ classification validators accept `nbr` and `sinapi` (regex widened)
- NBR 12721 validation rules added to the registry (S1..S11 cost groups)
- Brazilian-styled invoice PDF endpoint
  (`GET /api/v1/finance/invoices/{id}/br-pdf/`) — RPS layout with CNPJ /
  IE / IM / Razão Social / código de serviço / retenções block
- `Invoice.metadata.br_fields` extension point documented in
  `br_invoice_pdf.py` (the future SEFAZ bridge reads from here)
- en / de / ru validation messages include `nbr.*` keys
- Test coverage:
  `backend/tests/unit/test_brazil_invoice_pdf.py` (PDF render + BRL
  formatting), `backend/tests/unit/test_brazil_validation.py`
  (NBR 12721 rules)

What is NOT yet shipped (Tier-2):

## 1. SEFAZ NF-e generation (federal — goods)

Full Nota Fiscal Eletrônica issuance against the SEFAZ web-service.
Scope:

- XML schema 4.00 (current as of 2024) emit + validation against the
  official XSD bundle
- A1 / A3 digital certificate signing (XMLDSig, RSA-SHA256)
- Contingency flow (SVC-AN / SVC-RS) when the primary SEFAZ endpoint
  is unavailable
- CRC parity-protected 44-digit `chave de acesso` generation
- DANFE PDF renderer (the human-readable companion to the XML)
- Cancellation + correction-letter (CCe) endpoints
- Status query (`nfeStatusServico`) and event subscription
- Per-UF SEFAZ endpoint routing (each state has its own URL set)

Effort estimate: 15-20 dev-days. Owns its own service
(`services/sefaz-bridge/`) so the certificate handling can run isolated.

## 2. NFS-e (municipal — services)

Per-municipality Nota Fiscal de Serviço Eletrônica. There is NO single
national NFS-e standard — São Paulo (Web Service NFS-e SP),
Rio de Janeiro (Carioca Digital), Belo Horizonte (BHISS), Curitiba and
~60 other large cities each maintain their own RPS layout.

Pragmatic approach: ship a plug-in adapter pattern, start with the
ABRASF v2.04 standard (which ~70% of Brazilian municipalities accept),
then add SP / RJ / BH-specific adapters one by one.

Effort estimate: 8-12 dev-days for ABRASF + the three largest cities.

## 3. ICMS / ISS / PIS / COFINS calculation engine

A `BrazilTaxEngine` that, given an invoice line, returns the breakdown:

- ICMS (state VAT, 7-18% by UF, rules by CFOP code)
- IPI (federal manufacturing tax)
- ISS (municipal service tax, 2-5% by município)
- PIS + COFINS (regime cumulativo 3.65% / não-cumulativo 9.25%)
- CSLL + IRRF (when applicable to the tomador type)
- ICMS-ST (substitution) for goods that fall under the regime

This needs to be a stateful calculator because the rates are
configured per-tenant (CNAE, regime tributário — Simples Nacional vs.
Lucro Presumido vs. Lucro Real).

Effort estimate: 6-8 dev-days. Lives in `backend/app/modules/finance/`
alongside the invoice service.

## 4. SINAPI monthly importer

Caixa Econômica Federal publishes SINAPI (Sistema Nacional de Pesquisa
de Custos e Índices) monthly, per state, as Excel + PDF. The pricing
table is mandatory reference for federal public works.

Importer scope:

- Download from Caixa portal (HTTP redirect chain — there's no
  public API; the import is link-driven)
- Parse the published Excel workbook (composições + insumos sheets)
- Match against the project's UF column (rates differ per state)
- Surface as a "SINAPI 2026-04 SP" catalogue source in the costs
  module so estimators see it in the catalogue dropdown
- Schedule the importer monthly via Celery beat

Effort estimate: 4-6 dev-days. Needs Caixa portal credentials policy
(public download URLs change every month).

## 5. SPED Contribuições / DCTF export

Larger Brazilian customers carry SPED (Sistema Público de Escrituração
Digital) obligations. We can emit the SPED-Contribuições text-block
format directly from `oe_finance_ledger` rows. Worth scoping after
the SEFAZ NF-e bridge — same accountant persona, same auth fields.

Effort estimate: 4-5 dev-days.

## Open design questions

1. **Certificate storage** — A1 certs are .pfx files with a passphrase.
   Should we encrypt them at rest in `oe_finance_br_cert` or require
   per-call mTLS via mTLS-terminating reverse proxy? Decision impacts
   whether SEFAZ signing runs in the main FastAPI process or in a
   dedicated worker.
2. **Per-state vs national rates table** — ICMS varies by UF *and* by
   product class. Do we ship a comprehensive table (~5 MB JSON) or
   keep it tenant-overridable with sensible state defaults?
3. **Multi-CNPJ per tenant** — some construction groups operate multiple
   CNPJs (one per UF). Add `cnpj_id` to `oe_finance_invoice` or stay
   with a single per-tenant emitter?
4. **Demo mode** — for the open-source community edition, do we ship a
   sandbox SEFAZ flow that prints the XML to disk without signing?
   The signing infra requires a real certificate.

Owner: TBD. Linked feedback: 2026-05-27 João Vieira Esposito.
Contact for product follow-up: info@datadrivenconstruction.io.
