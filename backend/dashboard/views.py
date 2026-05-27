"""统计看板 Views"""
import io
from datetime import datetime, timedelta

from django.db.models import Count, Sum, Max
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils.timezone import make_aware
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import openpyxl

from users.models import User, Department
from users.permissions import IsDeptAdmin, IsSysAdmin
from chat.models import Conversation, Message


class OverviewView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        user = request.user
        is_sys = user.role == "sys_admin"

        # 用户统计
        users_qs = User.objects.all() if is_sys else User.objects.filter(department=user.department)
        total_users = users_qs.count()

        # 活跃用户（今天有对话的）
        from django.utils import timezone
        today = timezone.now().date()
        active_user_ids = (
            Conversation.objects.filter(created_at__date=today)
            .values_list("user_id", flat=True)
            .distinct()
        )
        if not is_sys:
            active_user_ids = active_user_ids.filter(user__department=user.department)
        active_users = len(set(active_user_ids))

        # 对话统计
        convs_qs = Conversation.objects.all() if is_sys else Conversation.objects.filter(user__department=user.department)
        total_conversations = convs_qs.count()

        # 反馈统计
        msgs_qs = Message.objects.all() if is_sys else Message.objects.filter(conversation__user__department=user.department)
        like_count = msgs_qs.filter(feedback="like").count()
        dislike_count = msgs_qs.filter(feedback="dislike").count()

        return Response({
            "total_users": total_users,
            "active_users": active_users,
            "total_conversations": total_conversations,
            "like_count": like_count,
            "dislike_count": dislike_count,
            "satisfaction_rate": round(like_count / (like_count + dislike_count) * 100, 1) if (like_count + dislike_count) > 0 else 0,
        })


class TrendView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        user = request.user
        is_sys = user.role == "sys_admin"
        qs = Conversation.objects.all() if is_sys else Conversation.objects.filter(user__department=user.department)
        qs = qs.annotate(date=TruncDate("created_at")).values("date").annotate(count=Count("id")).order_by("date")
        data = [{"date": str(item["date"]), "count": item["count"]} for item in qs if item["date"]]
        return Response(data)


class DepartmentCompareView(APIView):
    permission_classes = [IsAuthenticated, IsSysAdmin]

    def get(self, request):
        depts = Department.objects.annotate(
            user_count=Count("members"),
            conversation_count=Count("members__conversations"),
        )
        data = [{
            "department": d.name,
            "user_count": d.user_count,
            "conversation_count": d.conversation_count,
        } for d in depts]
        return Response(data)


class ExportView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        # Placeholder: returns JSON data for frontend to generate Excel
        user = request.user
        is_sys = user.role == "sys_admin"
        qs = Conversation.objects.select_related("user", "user__department")
        if not is_sys:
            qs = qs.filter(user__department=user.department)

        data = [{
            "id": c.id,
            "user": c.user.username,
            "department": c.user.department.name if c.user.department else "",
            "title": c.title,
            "message_count": c.messages.count(),
            "created_at": str(c.created_at),
        } for c in qs[:1000]]
        return Response(data)


# ── 反馈管理 & 用户统计 ──────────────────────────────────────────


def _feedback_qs(request):
    """构建反馈消息查询集（按角色隔离）"""
    user = request.user
    is_sys = user.role == "sys_admin"
    qs = Message.objects.filter(feedback__isnull=False).select_related(
        "conversation", "conversation__user", "conversation__user__department"
    )
    if not is_sys:
        qs = qs.filter(conversation__user__department=user.department)

    # 筛选条件
    fb_type = request.query_params.get("feedback")
    if fb_type in ("like", "dislike"):
        qs = qs.filter(feedback=fb_type)

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(conversation__user__username__icontains=search)

    dept_id = request.query_params.get("department_id")
    if dept_id and is_sys:
        qs = qs.filter(conversation__user__department_id=dept_id)

    date_start = request.query_params.get("date_start")
    if date_start:
        start_dt = make_aware(datetime.strptime(date_start, "%Y-%m-%d"))
        qs = qs.filter(created_at__gte=start_dt)

    date_end = request.query_params.get("date_end")
    if date_end:
        # 结束日期取次日零点（不含），确保包含整个结束日期
        end_dt = make_aware(
            datetime.strptime(date_end, "%Y-%m-%d") + timedelta(days=1)
        )
        qs = qs.filter(created_at__lt=end_dt)

    return qs.order_by("-created_at")


class FeedbackListView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        qs = _feedback_qs(request)
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        total = qs.count()
        items = qs[(page - 1) * page_size : page * page_size]

        data = []
        for m in items:
            conv = m.conversation
            u = conv.user
            data.append({
                "id": m.id,
                "conversation_id": conv.id,
                "user": u.username,
                "department": u.department.name if u.department else "",
                "conversation_title": conv.title,
                "content_preview": m.content[:200] if m.content else "",
                "feedback": m.feedback,
                "feedback_detail": m.feedback_detail,
                "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            })

        return Response({
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": data,
        })


class FeedbackExportView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        qs = _feedback_qs(request)[:5000]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "反馈数据"
        ws.append(["用户名", "部门", "会话标题", "消息内容", "反馈类型", "反馈原因", "反馈时间"])

        for m in qs:
            conv = m.conversation
            u = conv.user
            reasons = ""
            if m.feedback_detail:
                reasons = "、".join(m.feedback_detail.get("reasons", []))
                comment = m.feedback_detail.get("comment", "")
                if comment:
                    reasons = f"{reasons}（{comment}）" if reasons else comment
            ws.append([
                u.username,
                u.department.name if u.department else "",
                conv.title,
                m.content[:500] if m.content else "",
                "点赞" if m.feedback == "like" else "点踩",
                reasons,
                m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        resp = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="feedback_export.xlsx"'
        return resp


class UserStatsView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        user = request.user
        is_sys = user.role == "sys_admin"

        users_qs = User.objects.all() if is_sys else User.objects.filter(department=user.department)
        search = request.query_params.get("search")
        if search:
            users_qs = users_qs.filter(username__icontains=search)

        dept_id = request.query_params.get("department_id")
        if dept_id and is_sys:
            users_qs = users_qs.filter(department_id=dept_id)

        users_qs = users_qs.select_related("department")

        # 分页
        total = users_qs.count()
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        paged_qs = users_qs[(page - 1) * page_size : page * page_size]

        # 批量聚合，避免 N+1
        user_ids = list(paged_qs.values_list("id", flat=True))

        conv_counts = dict(
            Conversation.objects.filter(user_id__in=user_ids)
            .values_list("user_id")
            .annotate(cnt=Count("id"))
        )
        msg_counts = dict(
            Message.objects.filter(conversation__user_id__in=user_ids, role="user")
            .values_list("conversation__user_id")
            .annotate(cnt=Count("id"))
        )
        token_sums = dict(
            Message.objects.filter(conversation__user_id__in=user_ids)
            .values_list("conversation__user_id")
            .annotate(total=Sum("tokens_used"))
        )
        last_actives = dict(
            Conversation.objects.filter(user_id__in=user_ids)
            .values_list("user_id")
            .annotate(last=Max("created_at"))
        )

        data = []
        for u in paged_qs:
            data.append({
                "id": u.id,
                "username": u.username,
                "department": u.department.name if u.department else "",
                "conversation_count": conv_counts.get(u.id, 0),
                "message_count": msg_counts.get(u.id, 0),
                "tokens_used": token_sums.get(u.id) or 0,
                "last_active": last_actives.get(u.id).strftime("%Y-%m-%d %H:%M") if last_actives.get(u.id) else "",
            })

        return Response({"data": data, "total": total})
