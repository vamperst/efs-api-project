# VPC Interface Endpoints para SSM (Session Manager)
#
# A EC2 populator fica em subnet privada. Para o SSM Agent funcionar precisamos
# dos 3 endpoints: ssm, ssmmessages, ec2messages. Sem eles, o agente so
# consegue alcancar o control plane do SSM via NAT Gateway -> Internet.
#
# Com os endpoints: trafego SSM fica 100% dentro da VPC, mais rapido e confiavel.
#
# Controlado por var.enable_ssm_vpc_endpoints (default true).

# SG dedicado aos endpoints - aceita 443 de qualquer coisa dentro da VPC
resource "aws_security_group" "ssm_endpoints" {
  count       = var.enable_ssm_vpc_endpoints ? 1 : 0
  name        = "${var.project}-ssm-endpoints-sg"
  description = "HTTPS para VPC endpoints do SSM"
  vpc_id      = local.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.this.cidr_block] # atributo CIDR via data vpc
    description = "HTTPS de dentro da VPC"
  }

  egress {
    description = "Saida HTTPS para AWS APIs"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-ssm-endpoints-sg"
  })
}

locals {
  ssm_services = var.enable_ssm_vpc_endpoints ? ["ssm", "ssmmessages", "ec2messages"] : []
}

resource "aws_vpc_endpoint" "ssm" {
  for_each = toset(local.ssm_services)

  vpc_id              = local.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.private_subnet_ids
  security_group_ids  = [aws_security_group.ssm_endpoints[0].id]
  private_dns_enabled = true

  tags = merge(local.common_tags, {
    Name = "${var.project}-vpce-${each.value}"
  })
}
