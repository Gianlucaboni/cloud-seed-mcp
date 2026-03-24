###############################################################################
# outputs.tf — Per-project SA provisioning outputs
###############################################################################

output "project_sa_emails" {
  description = "Map of client project names to their SA emails (runtime, deploy, data)"
  value = {
    for name, mod in module.project_sa : name => {
      runtime = mod.runtime_sa_email
      deploy  = mod.deploy_sa_email
      data    = mod.data_sa_email
    }
  }
}

output "wif_provider_names" {
  description = "Map of client project names to their WIF provider resource names"
  value = {
    for name, mod in module.project_sa : name => mod.wif_provider_name
    if mod.wif_provider_name != ""
  }
}
