# PDIS acceptance job.
#
#
# Deliberately identical to jobspec.nomad in resources and concurrency. An
# acceptance environment sized differently validates correctness but not
# capacity, and capacity is what failed before: a 512 MB instance was
# OOM-killed mid-analysis. tests/test_jobspec_parity.py fails when they drift.
#
# Adapted from nomad-sre-patterns/examples/docker-pattern/jobspec.nomad. The
# platform conventions are kept exactly: region, datacenters, the linux and spot
# constraints, the `__PLACEHOLDER__` substitutions .drone.yml fills with sed, the
# `domain_prod` variable name, and the Traefik tag set including sticky sessions.
#
# Three deviations from that template, each because PDIS is not a one-container
# app. Flag these to SRE when they review:
#
#  1. Two groups: the API gateway, and the Next.js client, which is independent
#     of it.
#  2. Two images from one repository, named `__REPO__NAME__-api` and `-web`. The
#     template assumes one image per repo.
#  3. Path routing on the single production domain. The module grants one
#     hostname, and every backend route is under `/api`, so one prefix rule
#     splits gateway from client. This is also what keeps browser calls
#     same-origin, so the client bundle carries no API hostname.
#
# Secrets follow the platform pattern confirmed by SRE: stored in Drone and
# substituted here by sed, the same mechanism as the repo name and build number.

variable "domain_acc" {
  type        = string
  description = "The application's acceptance domain."
}

job "__REPO__NAME__-acc" {
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

  # ---- Gateway --------------------------------------------------------------
  #
  # count is 1, matching the topology this app ran on before. Raise it only after
  # watching one allocation's memory under load.
  group "api" {
    count = 1

    network {
      port "http" { to = 8000 }
    }

    service {
      name     = "__REPO__NAME__-acc-api"
      port     = "http"
      provider = "nomad"

      # Higher priority than the client's catch-all below, so the more specific
      # /api prefix wins. Sticky sessions matter more here than in the template:
      # an analysis is a single long NDJSON stream, and moving mid-stream ends it.
      tags = [
        "traefik.enable=true",
        "traefik.http.routers.__REPO__NAME___acc_api.rule=Host(`${var.domain_acc}`) && PathPrefix(`/api`)",
        "traefik.http.routers.__REPO__NAME___acc_api.entrypoints=https",
        "traefik.http.routers.__REPO__NAME___acc_api.tls=true",
        "traefik.http.routers.__REPO__NAME___acc_api.priority=10",
        "traefik.http.services.__REPO__NAME___acc_api.loadbalancer.sticky=true",
        "traefik.http.services.__REPO__NAME___acc_api.loadbalancer.sticky.cookie.secure=true",
        "traefik.http.services.__REPO__NAME___acc_api.loadbalancer.sticky.cookie.httpOnly=true"
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

    # Reserve headroom for two active analyses, including LibreOffice child
    # processes, retained page images and parallel model request payloads.
    # This is a starting allocation, not a measured worst-case requirement.
    # Reserve the full memory budget rather than relying on oversubscription.
    # MAX_CONCURRENT_RUNS is two, raised from one when memory went to 6 GiB;
    # further runs queue. Memory rose to 8 GiB, with runs still two, when the
    # 2 GiB ToolUniverse task beside it was removed: the job's footprint is
    # unchanged and both runs gain headroom. Measure peak memory under two
    # concurrent image-heavy runs before raising the run cap.
    task "api" {
      driver = "docker"

      config {
        image = "bmgfsre.azurecr.io/__REPO__NAME__-api:__BUILD__NUMBER__"
        ports = ["http"]
      }

      resources {
        cpu    = 2000
        memory = 8192
      }

      env {
        PORT                = "${NOMAD_PORT_http}"
        # Stated here although it is the default, because it is sized against the
        # memory above: the two are read, and changed, together.
        MAX_CONCURRENT_RUNS = "2"

        # Credentials, substituted by .drone.yml from Drone secrets, the same
        # mechanism as the repo name and build number.
        #
        # A consequence worth knowing: the substituted values land in the job
        # definition Nomad stores, so `nomad job inspect` in this namespace
        # shows them. Namespace access is what protects them.
        OPENAI_API_KEY           = "__OPENAI_API_KEY__"
        ANTHROPIC_API_KEY        = "__ANTHROPIC_API_KEY__"
        KONG_KEY                 = "__KONG_KEY__"
        NCBI_API_KEY             = "__NCBI_API_KEY__"
        TAVILY_API_KEY           = "__TAVILY_API_KEY__"
        SEMANTIC_SCHOLAR_API_KEY = "__SEMANTIC_SCHOLAR_API_KEY__"
        OPENFDA_API_KEY          = "__OPENFDA_API_KEY__"
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
      name     = "__REPO__NAME__-acc-web"
      port     = "http"
      provider = "nomad"

      # Catch-all for the same host, at lower priority so it never shadows the
      # /api rule above.
      tags = [
        "traefik.enable=true",
        "traefik.http.routers.__REPO__NAME___acc_web.rule=Host(`${var.domain_acc}`)",
        "traefik.http.routers.__REPO__NAME___acc_web.entrypoints=https",
        "traefik.http.routers.__REPO__NAME___acc_web.tls=true",
        "traefik.http.routers.__REPO__NAME___acc_web.priority=1",
        "traefik.http.services.__REPO__NAME___acc_web.loadbalancer.sticky=true",
        "traefik.http.services.__REPO__NAME___acc_web.loadbalancer.sticky.cookie.secure=true",
        "traefik.http.services.__REPO__NAME___acc_web.loadbalancer.sticky.cookie.httpOnly=true"
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
}
