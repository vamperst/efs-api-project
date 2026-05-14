# SG do ALB - HTTP 80 da internet
resource "aws_security_group" "alb" {
  name        = "${var.project}-s3-alb-sg"
  description = "ALB da API S3-backed"
  vpc_id      = local.vpc_id

  ingress {
    description = "HTTP publico"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-s3-alb-sg"
  })
}

# SG das tasks Fargate - so aceita o ALB na porta da API
resource "aws_security_group" "api" {
  name        = "${var.project}-s3-api-sg"
  description = "Fargate tasks da API S3-backed"
  vpc_id      = local.vpc_id

  ingress {
    description     = "ALB para API"
    from_port       = var.api_port
    to_port         = var.api_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-s3-api-sg"
  })
}

# A task Fargate precisa acessar o mount target S3 Files na porta NFS/2049.
resource "aws_security_group_rule" "s3files_from_api" {
  type                     = "ingress"
  from_port                = 2049
  to_port                  = 2049
  protocol                 = "tcp"
  security_group_id        = aws_security_group.s3files_mt.id
  source_security_group_id = aws_security_group.api.id
  description              = "NFS das tasks Fargate"
}
