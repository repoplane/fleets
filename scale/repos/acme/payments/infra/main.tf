resource "null_resource" "ok" {
  triggers = { name = var.name }
}
