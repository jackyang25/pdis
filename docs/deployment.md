# Deployment and releases

Local setup and development checks are in the [README](../README.md).

PDIS deploys to the foundation's Nomad cluster. Three files in this repository
describe it, and a fourth lives in the tenant repository.

| File | Owns |
| --- | --- |
| [.drone.yml](../.drone.yml) | Test, build, and push the three images; deploy to acceptance on merge and to production on promote |
| [jobspec.nomad](../jobspec.nomad) | The production job: two groups (API with its connector, and web), their resources, and the ingress rules |
| [jobspec_acc.nomad](../jobspec_acc.nomad) | The acceptance job, identical but for environment naming and hostname |
| `tf_nomad_tenant_configuration/prod/main` | The `module "aws-pdis"` block that creates the namespace and the CI secrets |

The client and the gateway share one hostname. Traefik routes `/api/*` to the
gateway and everything else to the client, which is why the client's bundle
carries no API hostname and why CORS is unset in production. The ToolUniverse
connector carries no routing tag at all: that absence is the only thing keeping
it off the public internet, and `tests/test_jobspec_parity.py` asserts it.

Onboarding is a pull request to `tf_nomad_tenant_configuration/prod/main`:

```hcl
module "aws-pdis" {
  source                   = "../_modules/aws_application"
  namespace                = "pdis"
  repo                     = "pdis"
  zone_id                  = var.zone_id
  cluster_ingress_hostname = var.aws_cluster_ingress_hostname
  docker_password          = var.docker_password
  acceptance_domain        = "pdis-acc.bmgf.io"
  production_domain        = "pdis.bmgf.io"
}
```

Merging it creates the Nomad namespace and the Drone secrets the pipeline
expects: `AWS_NOMAD_TOKEN`, `DOCKER_PASSWORD`, `NAMESPACE`,
`NOMAD_VAR_domain_acc_aws`, and `NOMAD_VAR_domain_prod_aws`. Activate the
repository at [cicd.bmgf.io](https://cicd.bmgf.io) first.

Acceptance deploys automatically on merge to `main`. Production is a manual
promote of a build that already passed acceptance:

```sh
drone build promote gatesfoundation/pdis <build> production
```

Both jobspecs and the pipeline are drafts pending reconciliation with
[nomad-sre-patterns](https://github.com/gatesfoundation/nomad-sre-patterns);
the entries marked `TODO` are cluster facts this repository cannot know.

## Analysis capacity

Both environments reserve 4096 MiB of memory and 2000 MHz of CPU for the API
task, including its LibreOffice subprocesses. There is no separate burst memory
limit: the full memory budget is reserved. Nomad's CPU allocation is in MHz, not
a count of cores. See the [Nomad resource specification](https://developer.hashicorp.com/nomad/docs/job-specification/resources).

Both environments temporarily limit processing to one active analysis; additional
runs wait for capacity.
Review checkpoints do not occupy an active processing slot. This allocation adds
headroom for slide rendering, retained images and parallel model requests; it is
a starting budget, not a guarantee for every document combination.

Before deployment, confirm cluster capacity and namespace quotas with the platform
team. The API and its 2048 MiB connector need 6 GiB together on one node, in
addition to node overhead; web allocations and rolling deployments need further
capacity. Measure peak memory during image-heavy runs before raising
the run limit. Exit status 137 suggests a killed process, but allocation events
and OOM logs are needed to confirm memory exhaustion.

## Product versions and release notes

[web/lib/releases.ts](../web/lib/releases.ts) owns the user-facing release history. The header and
`/updates` page read it; there is no second displayed version.
These are product versions, separate from package metadata, rubric revisions,
and saved-result schema versions. The displayed version identifies the code in
the running app, not its deployment status. Local, acceptance, and production
builds of the same version show the same notes.

- Assign a version when a coherent set of changes is ready. Add one `RELEASES`
  entry, newest first, and group its notes by tool or capability using `sections`.
  Short entries can omit section titles. Do not create an entry for every commit.
- The first entry supplies the header's version and the page's “This version”
  label. Include only changes implemented in that code. Keep plans and unfinished
  work in development notes, not the user-facing changelog.
- Do not add coding dates, planned deployment dates, or build numbers to these
  entries. Git records implementation history; deployment records track promotion.
  Historical dates and build numbers from the first three entries remain in Git.
- While on `0.x`, use a patch increment for compatible fixes/polish and a minor
  increment for new capabilities or breaking changes. State any required user
  action, such as rerunning Scout after an artifact-format change. From `1.0.0`
  onward, breaking changes require a major increment.
- Build and test the prepared release, then promote that same build to production.
  Retrying or redeploying the same release does not add an entry or bump its version.
- A deployment may include several versions prepared since the previous deployment.
  No Unreleased-to-release conversion or timestamp update is needed at deployment.
  Once a version has been distributed, put subsequent changes in a new version;
  do not reuse its identity for a different set of capabilities.
- Summarize user-visible changes since the previous version, not every commit.
  Lead with compatibility requirements and required actions. Describe observable
  behavior rather than internal refactors, model guarantees, or trivial styling edits.
  Preserve older entries as history, even when newer versions replace that behavior.
- Run the web tests and type check. Confirm the release label and notes during
  the deployment smoke check. No provider credentials or feedback are stored by
  this feature; the feedback popover directs users to Jack Yang or Shyam Bhaskaran
  on Teams.
