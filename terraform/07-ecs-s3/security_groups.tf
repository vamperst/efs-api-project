resource "aws_security_group" "alb" {
  name        = "${var.project}-s3-alb-sg"
  description = "ALB da API S3-backed"
  vpc_id      = local.vpc_id

  ingress {
    description = "HTTP publico do ALB"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Saida (stateful) para as EC2 do cluster"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.project}-s3-alb-sg" })
}

# SG das EC2 do cluster ECS. A task nao usa awsvpc aqui (usamos bridge para
# que o bind-mount com o Mountpoint funcione facil) - entao o ALB aponta
# diretamente para portas dinamicas na instancia.
resource "aws_security_group" "ecs_instance" {
  name        = "${var.project}-s3-ecs-instance-sg"
  description = "EC2 do cluster ECS S3"
  vpc_id      = local.vpc_id

  ingress {
    description     = "ALB para portas dinamicas ECS"
    from_port       = 32768
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Saida para S3/ECR/logs/SSM"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.project}-s3-ecs-instance-sg" })
}
