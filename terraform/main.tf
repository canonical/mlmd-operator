resource "juju_application" "mlmd" {
  charm {
    name     = "mlmd"
    channel  = var.channel
    revision = var.revision
  }
  config    = var.config
  model     = var.model_name
  name      = var.app_name
  resources = var.resources
  storage_directives = {
    mlmd-data = "10G"
  }
  trust     = true
  units     = 1
}
