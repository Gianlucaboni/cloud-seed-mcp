# Budget Policy Tests — Cloud Seed MCP

package terraform.test.budget

import future.keywords.in
import future.keywords.if
import data.terraform

# --------------------------------------------------------------------------- #
# Test: valid plan stays within budget (should produce no budget violations)
# --------------------------------------------------------------------------- #

test_valid_plan_within_budget if {
    result := terraform.deny with input as valid_plan
        with data.terraform.config as config
    budget_violations := {msg | msg := result[_]; contains(msg, "Budget")}
    count(budget_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test: plan that exceeds budget is denied
# --------------------------------------------------------------------------- #

test_over_budget_denied if {
    result := terraform.deny with input as over_budget_plan
        with data.terraform.config as config
    budget_violations := {msg | msg := result[_]; contains(msg, "Budget violation")}
    count(budget_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: single high-cost resource triggers per-resource warning
# --------------------------------------------------------------------------- #

test_high_cost_single_resource if {
    result := terraform.deny with input as high_cost_single_resource_plan
        with data.terraform.config as config_low_budget
    budget_warnings := {msg | msg := result[_]; contains(msg, "Budget warning")}
    count(budget_warnings) > 0
}

# --------------------------------------------------------------------------- #
# Test: no-op (delete) actions do not count toward budget
# --------------------------------------------------------------------------- #

test_delete_action_not_counted if {
    result := terraform.deny with input as delete_plan
        with data.terraform.config as config
    budget_violations := {msg | msg := result[_]; contains(msg, "Budget")}
    count(budget_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test configuration
# --------------------------------------------------------------------------- #

config := {
    "budget_limit_eur_monthly": 500,
    "allowed_regions": ["europe-west1", "europe-west4", "europe-west6"],
    "allowed_zones": ["europe-west1-b", "europe-west1-c", "europe-west1-d", "europe-west4-a", "europe-west4-b", "europe-west4-c", "europe-west6-a", "europe-west6-b", "europe-west6-c"],
    "allowed_resource_types": [
        "google_compute_instance", "google_storage_bucket", "google_cloud_run_service",
        "google_artifact_registry_repository", "google_sql_database_instance",
        "google_bigquery_dataset", "google_bigquery_table",
        "google_service_account", "google_project_service",
        "google_compute_network", "google_compute_subnetwork",
        "google_storage_bucket_iam_member", "google_storage_bucket_iam_binding",
        "google_project_iam_member", "google_project_iam_binding"
    ],
    "cost_estimates_eur_monthly": {
        "google_compute_instance": 25.0,
        "google_storage_bucket": 2.0,
        "google_cloud_run_service": 15.0,
        "google_artifact_registry_repository": 1.0,
        "google_sql_database_instance": 50.0,
        "google_bigquery_dataset": 0.0,
        "google_service_account": 0.0,
        "google_project_service": 0.0
    },
    "gpu_machine_type_prefixes": ["a2-", "g2-", "a3-"],
    "gpu_approval_flag": "cloud_seed_gpu_approved",
    "naming_pattern": "^[a-z][a-z0-9-]*$",
    "public_access_members": ["allUsers", "allAuthenticatedUsers"]
}

config_low_budget := object.union(config, {"budget_limit_eur_monthly": 80})

# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #

valid_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.web",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-web",
                    "machine_type": "e2-medium",
                    "zone": "europe-west1-b",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        },
        {
            "address": "google_storage_bucket.data",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-data",
                    "location": "europe-west1",
                    "encryption": [{"default_kms_key_name": "key"}]
                }
            }
        }
    ]
}

# 11 x Cloud SQL instances at 50 EUR each = 550 EUR > 500 EUR budget
over_budget_plan := {
    "resource_changes": [
        {
            "address": "google_sql_database_instance.db_01",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-01", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_02",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-02", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_03",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-03", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_04",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-04", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_05",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-05", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_06",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-06", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_07",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-07", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_08",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-08", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_09",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-09", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_10",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-10", "region": "europe-west1"}}
        },
        {
            "address": "google_sql_database_instance.db_11",
            "type": "google_sql_database_instance",
            "change": {"actions": ["create"], "after": {"name": "acme-db-11", "region": "europe-west1"}}
        }
    ]
}

# Single Cloud SQL at 50 EUR > 50% of 80 EUR budget
high_cost_single_resource_plan := {
    "resource_changes": [
        {
            "address": "google_sql_database_instance.expensive",
            "type": "google_sql_database_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-db-expensive",
                    "region": "europe-west1"
                }
            }
        }
    ]
}

delete_plan := {
    "resource_changes": [
        {
            "address": "google_sql_database_instance.old",
            "type": "google_sql_database_instance",
            "change": {
                "actions": ["delete"],
                "after": null
            }
        }
    ]
}

# --------------------------------------------------------------------------- #
# Infracost tests
# --------------------------------------------------------------------------- #

test_infracost_costs_used if {
    result := terraform.deny with input as infracost_plan
        with data.terraform.config as config
    budget_violations := {msg | msg := result[_]; contains(msg, "Budget")}
    count(budget_violations) == 0
}

test_infracost_expensive_exceeds_budget if {
    result := terraform.deny with input as infracost_expensive_plan
        with data.terraform.config as config
    budget_violations := {msg | msg := result[_]; contains(msg, "Budget violation")}
    count(budget_violations) > 0
}

test_infracost_single_resource_warning if {
    result := terraform.deny with input as infracost_single_expensive_plan
        with data.terraform.config as config
    budget_warnings := {msg | msg := result[_]; contains(msg, "Budget warning")}
    count(budget_warnings) > 0
}

test_fallback_to_static_when_no_infracost if {
    result := terraform.deny with input as valid_plan
        with data.terraform.config as config
    budget_violations := {msg | msg := result[_]; contains(msg, "Budget")}
    count(budget_violations) == 0
}

test_mixed_infracost_and_static if {
    result := terraform.deny with input as mixed_cost_plan
        with data.terraform.config as config
    budget_violations := {msg | msg := result[_]; contains(msg, "Budget")}
    count(budget_violations) == 0
}

# --------------------------------------------------------------------------- #
# Infracost test fixtures
# --------------------------------------------------------------------------- #

infracost_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.web",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "web",
                    "zone": "europe-west1-b",
                    "machine_type": "e2-medium",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        }
    ],
    "infracost_costs": {
        "google_compute_instance.web": 28.11
    }
}

infracost_expensive_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.big_vm",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "big-vm",
                    "zone": "europe-west1-b",
                    "machine_type": "n2-highmem-16",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        }
    ],
    "infracost_costs": {
        "google_compute_instance.big_vm": 758.34
    }
}

infracost_single_expensive_plan := {
    "resource_changes": [
        {
            "address": "google_sql_database_instance.prod_db",
            "type": "google_sql_database_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "prod-db",
                    "region": "europe-west1"
                }
            }
        }
    ],
    "infracost_costs": {
        "google_sql_database_instance.prod_db": 280.0
    }
}

mixed_cost_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.web",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "web",
                    "zone": "europe-west1-b",
                    "machine_type": "e2-medium",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        },
        {
            "address": "google_storage_bucket.data",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "data",
                    "location": "europe-west1",
                    "encryption": [{"default_kms_key_name": "key"}]
                }
            }
        }
    ],
    "infracost_costs": {
        "google_compute_instance.web": 28.11
    }
}
