terraform {
  required_version = ">= 1.10.0"
  required_providers {
    coder = {
      source  = "coder/coder"
      version = "2.19.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "3.3.0"
    }
  }
}

provider "coder" {}
provider "kubernetes" {}

data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

locals {
  # Coder imports/dry-runs have no owner; the pinned provider supplies these defaults.
  template_preview = data.coder_workspace_owner.me.name == "default" && data.coder_workspace_owner.me.email == "default@example.com"
  labels = {
    "app.kubernetes.io/name" = "coder-workspace"
    "labops.bingo/workspace" = "bingops-lab"
  }
}

resource "coder_agent" "main" {
  os                      = "linux"
  arch                    = "amd64"
  startup_script          = file("${path.module}/startup.sh")
  startup_script_behavior = "blocking"
  metadata {
    display_name = "Disque personnel"
    key          = "home_disk"
    script       = "coder stat disk --path /home/coder"
    interval     = 60
    timeout      = 5
  }
}

resource "kubernetes_deployment_v1" "lab" {
  count            = data.coder_workspace.me.start_count
  wait_for_rollout = true
  metadata {
    name      = "coder-bingops-lab"
    namespace = "coder-workspaces"
    labels    = local.labels
  }
  lifecycle {
    precondition {
      condition     = local.template_preview || (data.coder_workspace_owner.me.name == "bingops" && data.coder_workspace.me.name == "lab")
      error_message = "This template owns one workspace: bingops/lab, with a dedicated retained home and SSH port."
    }
  }
  spec {
    replicas = 1
    selector {
      match_labels = local.labels
    }
    strategy {
      type = "Recreate"
    }
    template {
      metadata {
        labels = local.labels
      }
      spec {
        automount_service_account_token = false
        security_context {
          run_as_non_root = true
          run_as_user     = 1000
          run_as_group    = 1000
          fs_group        = 1000
          seccomp_profile {
            type = "RuntimeDefault"
          }
        }
        host_aliases {
          ip        = "192.168.10.151"
          hostnames = ["coder.lab.bingo"]
        }
        container {
          name    = "dev"
          image   = "ghcr.io/bingops-com/homeops-dev:0.1.0"
          command = ["/bin/sh", "-c", coder_agent.main.init_script]
          env {
            name  = "CODER_AGENT_TOKEN"
            value = coder_agent.main.token
          }
          env {
            name  = "TZ"
            value = "Europe/Paris"
          }
          resources {
            requests = { cpu = "250m", memory = "512Mi" }
            limits   = { cpu = "2", memory = "4Gi" }
          }
          security_context {
            run_as_non_root            = true
            allow_privilege_escalation = false
            capabilities {
              drop = ["ALL"]
            }
          }
          port {
            name           = "ssh"
            container_port = 2222
          }
          readiness_probe {
            tcp_socket {
              port = 2222
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }
          volume_mount {
            name       = "home"
            mount_path = "/home/coder"
          }
          volume_mount {
            name       = "ssh-access"
            mount_path = "/etc/coder-ssh"
            read_only  = true
          }
        }
        volume {
          name = "home"
          persistent_volume_claim {
            claim_name = "coder-bingops-home"
          }
        }
        volume {
          name = "ssh-access"
          config_map {
            name = "coder-workspace-ssh"
          }
        }
      }
    }
  }
}
