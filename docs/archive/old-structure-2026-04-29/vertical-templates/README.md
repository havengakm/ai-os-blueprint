# Vertical Templates — per-client-cohort deployment configs

A **vertical template** is the bootstrap config for a new deployment. It declares which employees the deployment uses, which playbooks each owns, which integrations are wired, and which knowledge-base seed loads on creation.

The architecture is universal across deployments. Customisation lives only in vertical templates + per-deployment context/data — never in code.

## Structure

```
vertical-templates/<vertical>/
├── deployment.yaml          Employee roster + playbook list + integration manifest
├── icp.yaml                 industries, titles, employee_min/max, geographies
├── knowledge-seed/          Boilerplate knowledge files copied into new deployments
└── README.md
```

## Verticals

| Vertical | Status | Description |
|---|---|---|
| `creative-branding/` | Phase 3 | CLYMB Co's deployment template. Existing outbound work is the baseline. |
| `property-management/` | Phase 10 | First external-client cohort — US property management companies. New employees: Acquisitions Researcher, Tenant Relations Manager, Maintenance Coordinator, Rent Collection Manager, Owner Reporting Specialist, Marketing Specialist + Operations Director. |

Future verticals (B2B SaaS, ecommerce, agencies, healthcare, etc.) ship as additional directories alongside.

## Per-deployment isolation

When a new deployment is created from a vertical template:
- A fresh `client_id` is provisioned.
- All foundation tables (`employee_memory`, `daily_dispatches`, `weekly_recaps`, `learning_events`, `decision_log`, etc.) are scoped to this `client_id` — no cross-deployment data flow.
- The vertical template's `knowledge-seed/` is copied into the deployment's `data/knowledge/` per-client directory.
- Integrations declared in `deployment.yaml` are wired with the deployment's credentials.

## Status

Empty scaffold today. Phase 3 builds `creative-branding/` (CLYMB Co's existing config extracted into template form). Phase 10 builds `property-management/`.
