resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-s3-api"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_ecs_cluster" "this" {
  name = "${var.project}-s3-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = [aws_ecs_capacity_provider.asg.name]

  default_capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.asg.name
    base              = 1
    weight            = 100
  }
}

# Task definition: EC2 launch type, network_mode bridge para permitir
# dynamic port mapping e bindMount direto do host.
#
# IMPORTANTE: bindMount de /mnt/s3 (host) -> /mnt/efs (container).
# A API nao precisa nem saber que mudou: ela continua lendo /mnt/efs.
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-s3-api"
  network_mode             = "bridge"
  requires_compatibilities = ["EC2"]
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn
  cpu                      = "512"
  memory                   = "1024"

  volume {
    name      = "s3-data"
    host_path = local.s3_mount_path
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${local.ecr_repository_url}:${var.api_image_tag}"
      essential = true
      cpu       = 512
      memory    = 1024

      # Com bridge networking + sidecar ADOT, um container ve o outro via `links`.
      links = ["adot:adot"]

      portMappings = [{
        containerPort = var.api_port
        hostPort      = 0
        protocol      = "tcp"
      }]

      environment = [
        { name = "EFS_MOUNT_PATH", value = "/mnt/efs" },
        { name = "API_PORT", value = tostring(var.api_port) },
        { name = "STORAGE_VARIANT", value = "s3" },
        { name = "ENV", value = var.env },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "METRIC_NAMESPACE", value = local.metric_namespace },
        { name = "BENCH_RESULTS_BUCKET", value = local.results_bucket },
        { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "http://adot:4317" },
        { name = "OTEL_RESOURCE_ATTRIBUTES", value = "service.name=${var.project}-api,deployment.environment=${var.env},efs_s3_bench.variant=s3" },
        { name = "AWS_EMF_ENVIRONMENT", value = "Local" },
        { name = "AWS_EMF_NAMESPACE", value = local.metric_namespace },
      ]

      dependsOn = [{
        containerName = "adot"
        condition     = "START"
      }]

      mountPoints = [{
        sourceVolume  = "s3-data"
        containerPath = "/mnt/efs"
        readOnly      = false
      }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.api_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    },
    {
      name      = "adot"
      image     = "public.ecr.aws/aws-observability/aws-otel-collector:latest"
      essential = true
      cpu       = 128
      memory    = 256
      command   = ["--config=/etc/ecs/ecs-default-config.yaml"]

      portMappings = [
        { containerPort = 4317, protocol = "tcp" },
        { containerPort = 4318, protocol = "tcp" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = local.log_group_otel
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "adot-s3"
        }
      }
    }
  ])

  tags = local.common_tags
}

resource "aws_ecs_service" "api" {
  name            = "${var.project}-s3-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count

  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.asg.name
    weight            = 100
    base              = 1
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.api_port
  }

  ordered_placement_strategy {
    type  = "spread"
    field = "attribute:ecs.availability-zone"
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.http, aws_ecs_cluster_capacity_providers.this]

  tags = local.common_tags
}
