# SG do ALB - aceita HTTP 80 da internet
resource "aws_security_group" "alb" {
  name        = "${var.project}-alb-sg"
  description = "ALB da API"
  vpc_id      = local.vpc_id

  ingress {
    description = "HTTP publico do ALB"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Saida (stateful) para as tasks ECS"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-alb-sg"
  })
}

# SG das tasks ECS - so aceita trafego do ALB na porta da API
resource "aws_security_group" "api" {
  name        = "${var.project}-api-sg"
  description = "ECS tasks da API"
  vpc_id      = local.vpc_id

  ingress {
    description     = "De ALB para API"
    from_port       = var.api_port
    to_port         = var.api_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Saida para ECR/logs/EFS/SSM"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-api-sg"
  })
}

# Permitir que as tasks da API alcancem o EFS na porta NFS
resource "aws_security_group_rule" "efs_from_api" {
  type                     = "ingress"
  from_port                = 2049
  to_port                  = 2049
  protocol                 = "tcp"
  security_group_id        = local.efs_sg_id
  source_security_group_id = aws_security_group.api.id
  description              = "NFS das tasks ECS da API"
}
