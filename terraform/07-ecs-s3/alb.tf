resource "aws_lb" "api" {
  name               = "${var.project}-s3-alb"
  internal           = !var.alb_public
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.alb_public ? local.public_subnet_ids : local.private_subnet_ids

  tags = merge(local.common_tags, { Name = "${var.project}-s3-alb" })
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project}-s3-tg"
  port        = var.api_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = local.vpc_id

  health_check {
    path                = "/health"
    port                = tostring(var.api_port)
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }

  tags = merge(local.common_tags, { Name = "${var.project}-s3-tg" })
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
