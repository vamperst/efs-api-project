resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-api"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_ecs_cluster" "this" {
  name = "${var.project}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "efs-data"

    efs_volume_configuration {
      file_system_id     = local.efs_file_system_id
      transit_encryption = "ENABLED"

      authorization_config {
        access_point_id = local.efs_ap_id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${local.ecr_repository_url}:${var.api_image_tag}"
      essential = true

      portMappings = [{
        containerPort = var.api_port
        protocol      = "tcp"
      }]

      environment = [
        { name = "EFS_MOUNT_PATH", value = "/mnt/efs" },
        { name = "API_PORT", value = tostring(var.api_port) },
        { name = "STORAGE_VARIANT", value = "efs" },
        { name = "ENV", value = var.env },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "METRIC_NAMESPACE", value = local.metric_namespace },
        { name = "BENCH_RESULTS_BUCKET", value = local.results_bucket },
        { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "http://localhost:4317" },
        { name = "OTEL_RESOURCE_ATTRIBUTES", value = "service.name=${var.project}-api,deployment.environment=${var.env},efs_s3_bench.variant=efs" },
        { name = "AWS_EMF_ENVIRONMENT", value = "Local" },
        { name = "AWS_EMF_NAMESPACE", value = local.metric_namespace },
        { name = "MAX_CONCURRENT_BENCHES", value = "30" },
        { name = "BENCH_QUEUE_URL", value = local.sqs_bench_url },
      ]

      dependsOn = [{
        containerName = "adot"
        condition     = "START"
      }]

      mountPoints = [{
        containerPath = "/mnt/efs"
        sourceVolume  = "efs-data"
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
      # Carrega a config da env AOT_CONFIG_CONTENT (envsubst $AOT_CONFIG_CONTENT)
      command = ["--config=env:AOT_CONFIG_CONTENT"]

      environment = [
        {
          name = "AOT_CONFIG_CONTENT"
          # indexed_attributes transforma span attributes em X-Ray Annotations
          # (filtraveis no console/service map).
          value = <<-YAML
            receivers:
              otlp:
                protocols:
                  grpc:
                    endpoint: 0.0.0.0:4317
                  http:
                    endpoint: 0.0.0.0:4318

            processors:
              batch/traces:
                timeout: 1s
                send_batch_size: 50
              batch/metrics:
                timeout: 60s

            exporters:
              awsxray:
                region: ${var.aws_region}
                indexed_attributes: [variant, bench_id, kind, op, size_bucket]
              awsemf:
                region: ${var.aws_region}
                namespace: ${local.metric_namespace}
                dimension_rollup_option: NoDimensionRollup
              debug:
                verbosity: normal

            service:
              pipelines:
                traces:
                  receivers: [otlp]
                  processors: [batch/traces]
                  exporters: [awsxray]
                metrics:
                  receivers: [otlp]
                  processors: [batch/metrics]
                  exporters: [awsemf, debug]
          YAML
        },
      ]

      portMappings = [
        { containerPort = 4317, protocol = "tcp" },
        { containerPort = 4318, protocol = "tcp" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = local.log_group_otel
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "adot-efs"
        }
      }
    }
  ])

  tags = local.common_tags
}

resource "aws_ecs_service" "api" {
  name            = "${var.project}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.private_subnet_ids
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.api_port
  }

  depends_on = [aws_lb_listener.http]

  tags = local.common_tags
}
