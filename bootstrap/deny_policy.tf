###############################################################################
# deny_policy.tf — IAM Deny Policies for the Orchestrator SA
#
# These policies implement the "Red" action classification from CLAUDE.md:
#   - No project deletion
#   - No modification of higher-level SAs (Installer, Orchestrator)
#   - No disabling the policy engine
#   - No accessing credentials from other projects
#
# Uses google_iam_deny_policy (requires google-beta provider and
# IAM v2 API / org-level permissions).
###############################################################################

# =============================================================================
# DENY POLICY: Block destructive project operations
# =============================================================================
# Prevents the Orchestrator from deleting GCP projects. Projects can be
# created and managed, but never deleted — that requires manual intervention.
# =============================================================================

resource "google_iam_deny_policy" "deny_project_deletion" {
  provider = google-beta

  parent       = urlencode("cloudresourcemanager.googleapis.com/organizations/${var.org_id}")
  name         = "cloudseed-deny-project-deletion"
  display_name = "Cloud Seed: Deny Project Deletion"

  rules {
    description = "Block the Orchestrator SA from deleting any GCP project"
    deny_rule {
      denied_principals = [
        "principalSet://goog/subject/${google_service_account.orchestrator.email}",
      ]
      denied_permissions = [
        "cloudresourcemanager.googleapis.com/projects.delete",
      ]
    }
  }
}

# =============================================================================
# DENY POLICY: Protect higher-level Service Accounts
# =============================================================================
# The Orchestrator must not be able to modify, disable, or delete the
# Installer SA or its own SA. This prevents privilege escalation.
# =============================================================================

resource "google_iam_deny_policy" "deny_modify_critical_sas" {
  provider = google-beta

  parent       = urlencode("cloudresourcemanager.googleapis.com/projects/${var.seed_project_id}")
  name         = "cloudseed-deny-modify-critical-sas"
  display_name = "Cloud Seed: Protect Critical SAs"

  rules {
    description = "Block the Orchestrator from modifying or deleting the Installer and Orchestrator SAs"
    deny_rule {
      denied_principals = [
        "principalSet://goog/subject/${google_service_account.orchestrator.email}",
      ]
      denied_permissions = [
        "iam.googleapis.com/serviceAccounts.delete",
        "iam.googleapis.com/serviceAccounts.disable",
        "iam.googleapis.com/serviceAccounts.update",
        "iam.googleapis.com/serviceAccounts.setIamPolicy",
      ]
      denial_condition {
        title       = "Only protect Installer and Orchestrator SAs"
        description = "Deny applies only when the target is the Installer or Orchestrator SA"
        expression  = <<-EOT
          resource.name.startsWith("projects/${var.seed_project_id}/serviceAccounts/${google_service_account.installer.unique_id}") ||
          resource.name.startsWith("projects/${var.seed_project_id}/serviceAccounts/${google_service_account.orchestrator.unique_id}")
        EOT
      }
    }
  }
}

# =============================================================================
# DENY POLICY: Block IAM policy modifications on the seed project
# =============================================================================
# The Orchestrator should not be able to modify IAM bindings on the seed
# project itself — only on client projects. This prevents it from granting
# itself additional permissions.
# =============================================================================

resource "google_iam_deny_policy" "deny_seed_iam_modification" {
  provider = google-beta

  parent       = urlencode("cloudresourcemanager.googleapis.com/projects/${var.seed_project_id}")
  name         = "cloudseed-deny-seed-iam-modification"
  display_name = "Cloud Seed: Protect Seed Project IAM"

  rules {
    description = "Block the Orchestrator from modifying IAM policies on the seed project"
    deny_rule {
      denied_principals = [
        "principalSet://goog/subject/${google_service_account.orchestrator.email}",
      ]
      denied_permissions = [
        "resourcemanager.googleapis.com/projects.setIamPolicy",
      ]
    }
  }
}

# =============================================================================
# DENY POLICY: Block access to Secret Manager of other projects
# =============================================================================
# Each project's secrets are isolated. The Orchestrator cannot read secrets
# from client projects — only the per-project SAs can, and only in their
# own project.
# =============================================================================

resource "google_iam_deny_policy" "deny_cross_project_secrets" {
  provider = google-beta

  parent       = urlencode("cloudresourcemanager.googleapis.com/organizations/${var.org_id}")
  name         = "cloudseed-deny-cross-project-secrets"
  display_name = "Cloud Seed: Deny Cross-Project Secret Access"

  rules {
    description = "Block the Orchestrator from accessing secrets in any project"
    deny_rule {
      denied_principals = [
        "principalSet://goog/subject/${google_service_account.orchestrator.email}",
      ]
      denied_permissions = [
        "secretmanager.googleapis.com/versions.access",
        "secretmanager.googleapis.com/secrets.get",
      ]
    }
  }
}
