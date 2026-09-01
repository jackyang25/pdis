# PDIS production job.
#
# Adapted from nomad-sre-patterns/examples/docker-pattern/jobspec.nomad. The
# platform conventions are kept exactly: region, datacenters, the linux and spot
# constraints, the `__PLACEHOLDER__` substitutions .drone.yml fills with sed, the
# `domain_prod` variable name, and the Traefik tag set including sticky sessions.
#
# Four deviations from that template, each because PDIS is not a one-container
# app. Flag these to SRE when they review:
#
#  1. Three groups, not one. The gateway, the client, and the private
#     ToolUniverse connector are one deployable unit: the client is useless
#     without the gateway, and the gateway loses retrieval without the connector.
#  2. Three images from one repository, named `__REPO__NAME__-api`,
#     `-web`, and `-tooluniverse`. The template assumes one image per repo.
#  3. Path routing on the single production domain. The module grants one
#     hostname, and every backend route is under `/api`, so one prefix rule
#     splits gateway from client. This is also what keeps browser calls
#     same-origin, so the client bundle carries no API hostname.
#  4. `count` and `resources` differ per group, and the gateway carries far more
#     memory than the template's 512 MB. See the sizing note on that group.

variable "domain_prod" {
  type        = string
  description = "The application's production domain."
}

job "__REPO__NAME__" {
  region      = "us-west-2"
  datacenters = ["dc1"]
  type        = "service"
  namespace   = "__NAMESPACE__"

  constraint {
    attribute = attr.kernel.name
    value     = "linux"
  }

  constraint {
    attribute = node.class
    value     = "spot"
  }

  # Only what differs from Nomad's service-job defaults. `auto_revert` is off by
  # default and is the one behaviour Render gave for free; `progress_deadline`
  # rises from 10m because the gateway image carries LibreOffice and is slow to
  # pull onto a cold node. Restart and reschedule stay at their defaults, which
  # already retry a task and move a lost allocation: instances are spot,
  # services are stateless, and the client holds the result (AGENTS.md), so a
  # reclaimed allocation costs a re-run and nothing else.
  update {
    auto_revert       = true
    progress_deadline = "15m"
  }

  # ---- Gateway -------------------------------------------------------------

  group "api" {
    count = 2

    network {
      port "http" { to = 8000 }
    }



    service {
      name     = "__REPO__NAME__-api"
      port     = "http"
      provider = "nomad"

      # Higher priority than the client's catch-all below, so the more specific
      # /api prefix wins. Sticky sessions matter more here than in the template:
      # an analysis is a single long NDJSON stream, and moving mid-stream ends it.
      tags = [
        "traefik.enable=true",
        "traefik.http.routers.__REPO__NAME___api.rule=Host(`${var.domain_prod}`) && PathPrefix(`/api`)",
        "traefik.http.routers.__REPO__NAME___api.entrypoints=https",
        "traefik.http.routers.__REPO__NAME___api.tls=true",
        "traefik.http.routers.__REPO__NAME___api.priority=10",
        "traefik.http.services.__REPO__NAME___api.loadbalancer.sticky=true",
        "traefik.http.services.__REPO__NAME___api.loadbalancer.sticky.cookie.secure=true",
        "traefik.http.services.__REPO__NAME___api.loadbalancer.sticky.cookie.httpOnly=true"
      ]

      check {
        type     = "http"
        path     = "/api/health"
        interval = "30s"
        timeout  = "5s"

        check_restart {
          # LibreOffice and the model clients make startup slow; failing fast
          # here would restart a task that was about to become healthy.
          grace = "60s"
          limit = 3
        }
      }
    }

    # Sized from a measured run, not from the template's default. One analysis
    # peaks near 530 MB: a 26-variable rubric issues ~90 model calls with up to
    # 24 in flight (MAX_PARALLEL_SECTIONS x MAX_PARALLEL_UNIT_CALLS, 4 x 6, both
    # in services/inspector/stages/assessor.py), each holding a request and a
    # response alongside the parsed document and a LibreOffice process.
    # MAX_CONCURRENT_RUNS admits two per allocation, so ~1.1 GB over an ~80 MB
    # baseline.
    #
    # This limit and MAX_CONCURRENT_RUNS are one decision. Raising the memory
    # without raising the cap wastes it; raising the cap without the memory gets
    # the allocation OOM-killed, which is what happened on a 512 MB instance.
    # Change them together or not at all.
    task "api" {
      driver = "docker"

      config {
        image = "bmgfsre.azurecr.io/__REPO__NAME__-api:__BUILD__NUMBER__"
        ports = ["http"]
      }

      resources {
        cpu        = 1000
        memory     = 2048
        memory_max = 2560
      }

      env {
        PORT                = "${NOMAD_PORT_http}"
        MAX_CONCURRENT_RUNS = "2"

        # Allocation stdout is read by an aggregator, not a person.
        LOG_FORMAT = "json"
        LOG_LEVEL  = "INFO"
      }

      # The connector's address comes from service discovery, not an env
      # interpolation: `NOMAD_PORT_*` only names ports in this task's own group,
      # so writing the connector's port that way silently yields this group's
      # port instead. `api/deps.py` reads TOOLUNIVERSE_BASE_URL, so this needs no
      # code change.
      template {
        data        = <<-EOH
          TOOLUNIVERSE_BASE_URL="http://{{ range nomadService "__REPO__NAME__-tooluniverse" }}{{ .Address }}:{{ .Port }}{{ end }}"
        EOH
        destination = "local/tooluniverse.env"
        env         = true
        change_mode = "restart"
      }

      # Credentials come from the cluster's secret store, never from this file.
      # tests/test_deploy_secrets.py enforces that no manifest carries a literal.
      #
      # DRAFT - the platform examples show no secret handling, so this is written
      # against Nomad Variables. Confirm with SRE whether the cluster fronts
      # Vault; if so, swap `nomadVar` for `{{ with secret "..." }}` and the
      # variable names and shape stay as they are.
      template {
        data        = <<-EOH
          {{- with nomadVar "nomad/jobs/__REPO__NAME__" }}
          OPENAI_API_KEY={{ .openai_api_key }}
          ANTHROPIC_API_KEY={{ .anthropic_api_key }}
          NCBI_API_KEY={{ .ncbi_api_key }}
          TAVILY_API_KEY={{ .tavily_api_key }}
          TOOLUNIVERSE_API_TOKEN={{ .tooluniverse_api_token }}
          {{- end }}
        EOH
        destination = "secrets/providers.env"
        env         = true
        change_mode = "restart"
      }
    }
  }

  # ---- Client --------------------------------------------------------------

  group "web" {
    count = 2

    network {
      port "http" { to = 3000 }
    }



    service {
      name     = "__REPO__NAME__-web"
      port     = "http"
      provider = "nomad"

      # Catch-all for the same host, at lower priority so it never shadows the
      # /api rule above.
      tags = [
        "traefik.enable=true",
        "traefik.http.routers.__REPO__NAME___web.rule=Host(`${var.domain_prod}`)",
        "traefik.http.routers.__REPO__NAME___web.entrypoints=https",
        "traefik.http.routers.__REPO__NAME___web.tls=true",
        "traefik.http.routers.__REPO__NAME___web.priority=1",
        "traefik.http.services.__REPO__NAME___web.loadbalancer.sticky=true",
        "traefik.http.services.__REPO__NAME___web.loadbalancer.sticky.cookie.secure=true",
        "traefik.http.services.__REPO__NAME___web.loadbalancer.sticky.cookie.httpOnly=true"
      ]

      check {
        type     = "http"
        path     = "/"
        interval = "30s"
        timeout  = "5s"
      }
    }

    # Stateless Next.js standalone server. It holds no analysis state, so it
    # needs far less than the gateway.
    task "web" {
      driver = "docker"

      config {
        image = "bmgfsre.azurecr.io/__REPO__NAME__-web:__BUILD__NUMBER__"
        ports = ["http"]
      }

      resources {
        cpu    = 500
        memory = 512
      }

      env {
        PORT     = "${NOMAD_PORT_http}"
        HOSTNAME = "0.0.0.0"
      }
    }
  }

  # ---- Private connector ---------------------------------------------------
  #
  # No Traefik tags anywhere in this group, and that absence is the only thing
  # keeping the connector off the ingress. It holds SEMANTIC_SCHOLAR_API_KEY and
  # authenticates with a bearer token only, so adding `traefik.enable=true` here
  # would publish it. Review changes to this group's tags as a security change.

  group "tooluniverse" {
    count = 1

    network {
      port "http" { to = 8080 }
    }



    service {
      name     = "__REPO__NAME__-tooluniverse"
      port     = "http"
      provider = "nomad"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "5s"
      }
    }

    # Retrieval fans out to searcher's global_worker_limit (48) concurrent calls
    # per run, and each gateway allocation admits MAX_CONCURRENT_RUNS at once, so
    # this single-worker process can hold many requests and their responses.
    # That exceeded 512 MB and was killed. Raising the gateway's cap or its count
    # raises this ceiling too.
    task "tooluniverse" {
      driver = "docker"

      config {
        image = "bmgfsre.azurecr.io/__REPO__NAME__-tooluniverse:__BUILD__NUMBER__"
        ports = ["http"]
      }

      resources {
        cpu    = 1000
        memory = 2048
      }

      env {
        PORT = "8080"
      }

      template {
        data        = <<-EOH
          {{- with nomadVar "nomad/jobs/__REPO__NAME__" }}
          TOOLUNIVERSE_API_TOKEN={{ .tooluniverse_api_token }}
          SEMANTIC_SCHOLAR_API_KEY={{ .semantic_scholar_api_key }}
          {{- end }}
        EOH
        destination = "secrets/connector.env"
        env         = true
        change_mode = "restart"
      }
    }
  }
}
