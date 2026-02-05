output "app_name" {
  value = juju_application.mlmd.name
}

output "provides" {
  value = {
    grpc                 = "grpc",
    velero_backup_config = "velero-backup-config"
  }
}

output "requires" {
  value = {
    logging = "logging"
  }
}
