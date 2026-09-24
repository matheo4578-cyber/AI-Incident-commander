variable "aws_region" {
  description = "AWS region for every resource."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Lowercase resource name prefix."
  type        = string
  default     = "ai-incident-commander"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,31}$", var.project_name))
    error_message = "project_name must be 3-32 lowercase letters, numbers, or hyphens."
  }
}

variable "kubernetes_version" {
  description = "An EKS Kubernetes version supported in the selected region."
  type        = string
  default     = "1.34"
}

variable "cluster_public_access_cidrs" {
  description = "CIDRs allowed to reach the authenticated EKS API endpoint."
  type        = list(string)
  validation {
    condition = length(var.cluster_public_access_cidrs) > 0 && alltrue([
      for cidr in var.cluster_public_access_cidrs : can(cidrnetmask(cidr)) && endswith(cidr, "/32")
    ])
    error_message = "Every EKS public-access entry must be a valid single-host IPv4 /32 CIDR."
  }
}

variable "node_instance_type" {
  description = "EKS managed node instance type."
  type        = string
  default     = "t3.medium"
}
