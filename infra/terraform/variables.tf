variable "aws_region" {
  type        = string
  description = "AWS region for the deployment."
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  description = "Deployment profile. Production enables HA and deletion protection."
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}

variable "container_image" {
  type        = string
  description = "Immutable ECR image URI including a commit-SHA tag."
}

variable "pms_provider" {
  type        = string
  description = "Use mock in credential-free staging; production requires cliniko."
  default     = "mock"

  validation {
    condition     = contains(["mock", "cliniko"], var.pms_provider)
    error_message = "pms_provider must be mock or cliniko"
  }
}

variable "certificate_arn" {
  type        = string
  description = "Optional ACM certificate ARN. Required before production voice traffic."
  default     = null
  nullable    = true
}

variable "desired_count_staging" {
  type    = number
  default = 1
}

variable "desired_count_production" {
  type    = number
  default = 2
}

variable "database_name" {
  type    = string
  default = "voice_agent"
}

variable "database_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "alert_email" {
  type        = string
  description = "Optional operations email. Subscription must be confirmed manually."
  default     = null
  nullable    = true
}
