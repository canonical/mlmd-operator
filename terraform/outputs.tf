output "app_name" {
  value = juju_application.mlmd.name
}

output "provides" {
  value = {
    grpc  = "grpc",
  }
}

output "requires" {
  value = {
    logging        = "logging"
  }
}
