"""组织架构 & 用户管理 Views"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.hashers import make_password
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import serializers
import openpyxl

from users.models import User, Department, UserKBPermission, UserAgentPermission, KnowledgeBase
from knowledge.minio_client import get_minio_client
from users.permissions import IsDeptAdmin, IsSysAdmin


def _check_dept_scope(request, target_user):
    """部门管理员只能操作本部门且非系统管理员的用户，返回错误 Response 或 None"""
    if request.user.role == "sys_admin":
        return None
    if target_user.department_id != request.user.department_id:
        return Response({"error": "无权操作此用户"}, status=403)
    if target_user.role == "sys_admin":
        return Response({"error": "无权操作系统管理员"}, status=403)
    return None


# ── Serializers ────────────────────────────────────────────────

class DepartmentSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, default="")
    member_count = serializers.IntegerField(read_only=True, default=0)


class UserListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    phone = serializers.CharField()
    role = serializers.CharField()
    department = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    is_active = serializers.BooleanField()
    date_joined = serializers.DateTimeField()

    def get_department(self, obj):
        return {"id": obj.department_id, "name": obj.department.name if obj.department else None}

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        url = f"/api/org/users/{obj.id}/avatar/"
        if request:
            return request.build_absolute_uri(url)
        return url


class CreateUserSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=6)
    phone = serializers.CharField(max_length=20)
    role = serializers.ChoiceField(choices=["user"])
    department_id = serializers.IntegerField(required=False)


# ── Department Views ───────────────────────────────────────────

class DepartmentListView(APIView):
    permission_classes = [IsAuthenticated, IsSysAdmin]

    def get(self, request):
        depts = Department.objects.all()
        data = []
        for d in depts:
            data.append({
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "member_count": d.members.count(),
            })
        return Response(data)

    def post(self, request):
        name = request.data.get("name", "").strip()
        if not name:
            return Response({"error": "部门名称不能为空"}, status=400)
        dept, created = Department.objects.get_or_create(name=name, defaults={
            "description": request.data.get("description", "")
        })
        if not created:
            return Response({"error": "部门已存在"}, status=400)
        return Response({"id": dept.id, "name": dept.name}, status=201)


class DepartmentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSysAdmin]

    def put(self, request, pk):
        dept = get_object_or_404(Department, pk=pk)
        dept.name = request.data.get("name", dept.name)
        dept.description = request.data.get("description", dept.description)
        dept.save()
        return Response({"id": dept.id, "name": dept.name})

    def delete(self, request, pk):
        dept = get_object_or_404(Department, pk=pk)
        # 将该部门下所有用户的部门字段置空，归入"未分配"状态
        from users.models import User
        User.objects.filter(department=dept).update(department=None)
        dept.delete()
        return Response({"message": "已删除"})


# ── User Views ────────────────────────────────────────────────

class UserListView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        qs = User.objects.select_related("department")
        if request.user.role != "sys_admin":
            qs = qs.filter(department=request.user.department).exclude(role="sys_admin")
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(username__icontains=search) | qs.filter(phone__icontains=search)

        # 分页
        total = qs.count()
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        users = qs[(page - 1) * page_size : page * page_size]

        data = UserListSerializer(users, many=True, context={"request": request}).data
        return Response({"data": data, "total": total})


class UserCreateView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request):
        ser = CreateUserSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        if User.objects.filter(username=d["username"]).exists():
            return Response({"error": "用户名已存在"}, status=400)
        if User.objects.filter(phone=d["phone"]).exists():
            return Response({"error": "手机号已存在"}, status=400)

        dept_id = d.get("department_id")
        if request.user.role != "sys_admin":
            dept_id = request.user.department_id

        user = User.objects.create_user(
            username=d["username"],
            password=d["password"],
            phone=d["phone"],
            role=d["role"],
            department_id=dept_id,
        )
        return Response({"id": user.id, "username": user.username}, status=201)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        err = _check_dept_scope(request, user)
        if err:
            return err
        return Response(UserListSerializer(user).data)

    def put(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        err = _check_dept_scope(request, user)
        if err:
            return err

        username = request.data.get("username")
        if username is not None:
            username = username.strip()
            if not username:
                return Response({"error": "用户名不能为空"}, status=400)
            if User.objects.filter(username=username).exclude(pk=pk).exists():
                return Response({"error": "用户名已存在"}, status=400)
            user.username = username

        phone = request.data.get("phone")
        if phone is not None:
            phone = phone.strip()
            if not phone:
                return Response({"error": "手机号不能为空"}, status=400)
            if User.objects.filter(phone=phone).exclude(pk=pk).exists():
                return Response({"error": "手机号已存在"}, status=400)
            user.phone = phone

        role = request.data.get("role")
        if role is not None:
            if request.user.role != "sys_admin" and role == "sys_admin":
                return Response({"error": "无权设置系统管理员"}, status=403)
            user.role = role

        department_id = request.data.get("department_id")
        if department_id is not None and request.user.role == "sys_admin":
            user.department_id = department_id if department_id else None

        user.save()
        return Response(UserListSerializer(user).data)

    def delete(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.pk == request.user.pk:
            return Response({"error": "不能删除自己"}, status=400)
        err = _check_dept_scope(request, target)
        if err:
            return err
        target.delete()
        return Response({"message": "已删除"})


class ResetPasswordView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        err = _check_dept_scope(request, user)
        if err:
            return err
        new_pwd = request.data.get("new_password", "123456")
        user.set_password(new_pwd)
        user.save()
        return Response({"message": "密码已重置"})


class ToggleActiveView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        err = _check_dept_scope(request, user)
        if err:
            return err
        user.is_active = not user.is_active
        user.save()
        return Response({"is_active": user.is_active})


class TransferUserView(APIView):
    permission_classes = [IsAuthenticated, IsSysAdmin]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        dept_id = request.data.get("department_id")
        if not dept_id:
            return Response({"error": "需要指定 department_id"}, status=400)
        user.department_id = dept_id
        user.save()
        return Response({"message": "已调动"})


class BatchImportView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "请上传 Excel 文件"}, status=400)

        try:
            wb = openpyxl.load_workbook(upload)
            ws = wb.active
        except Exception as e:
            return Response({"error": f"Excel 解析失败: {e}"}, status=400)

        created, errors = [], []
        default_dept = request.user.department if request.user.role != "sys_admin" else None

        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            username, password, role = (row[0], row[1] if len(row) > 1 else "123456",
                                         row[2] if len(row) > 2 else "user")
            phone = row[3] if len(row) > 3 else None
            if not username:
                continue
            # 部门管理员不能创建系统管理员
            if str(role) == "sys_admin" and request.user.role != "sys_admin":
                errors.append(f"行{i}: 无权创建系统管理员")
                continue
            if User.objects.filter(username=str(username)).exists():
                errors.append(f"行{i}: 用户名 {username} 已存在")
                continue
            if phone and User.objects.filter(phone=str(phone)).exists():
                errors.append(f"行{i}: 手机号 {phone} 已存在")
                continue
            user = User.objects.create_user(
                username=str(username),
                password=str(password),
                phone=str(phone) if phone else str(username),
                role=str(role),
                department=default_dept,
            )
            created.append(user.username)

        return Response({"created": created, "errors": errors, "total": len(created)})


class KBPermissionView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        err = _check_dept_scope(request, user)
        if err:
            return err
        perms = UserKBPermission.objects.filter(user=user).select_related("knowledge_base")
        data = [{"kb_id": p.knowledge_base.kb_id, "name": p.knowledge_base.name} for p in perms]
        return Response(data)

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        err = _check_dept_scope(request, user)
        if err:
            return err
        kb_ids = request.data.get("kb_ids", [])
        UserKBPermission.objects.filter(user=user).delete()
        for kb_id in kb_ids:
            kb = KnowledgeBase.objects.filter(kb_id=kb_id).first()
            if not kb:
                continue
            # dept_admin 只能分配本部门的知识库
            if (
                request.user.role != "sys_admin"
                and kb.department_id != request.user.department_id
            ):
                continue
            UserKBPermission.objects.create(
                user=user, knowledge_base=kb, granted_by=request.user
            )
        return Response({"message": "权限已更新"})


class AgentPermissionView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        err = _check_dept_scope(request, user)
        if err:
            return err
        perms = UserAgentPermission.objects.filter(user=user)
        data = [{"agent_name": p.agent_name} for p in perms]
        return Response(data)

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        err = _check_dept_scope(request, user)
        if err:
            return err
        agent_names = request.data.get("agent_names", [])
        UserAgentPermission.objects.filter(user=user).delete()
        for name in agent_names:
            UserAgentPermission.objects.create(user=user, agent_name=name)
        return Response({"message": "权限已更新"})


class UserAvatarView(APIView):
    """管理员查看任意用户的头像（支持 ?token= query 参数认证，用于 img src）"""

    def get_permissions(self):
        # GET/HEAD 请求支持 query token 认证（img src 无法发送 Header）
        if self.request.method in ("GET", "HEAD"):
            raw_token = self.request.query_params.get("token", "")
            if raw_token:
                return [AllowAny()]
        return [IsAuthenticated(), IsDeptAdmin()]

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        # query token 认证（img src 无法发送 Header）
        raw_token = request.query_params.get("token", "")
        if raw_token:
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                access_token = AccessToken(raw_token)
                requester = User.objects.get(
                    id=access_token["user_id"], is_active=True
                )
            except Exception:
                return HttpResponse(status=401)
            if requester.role not in ("sys_admin", "dept_admin"):
                return HttpResponse(status=403)
            if requester.role == "dept_admin" and user.department_id != requester.department_id:
                return HttpResponse(status=403)
        else:
            # Header JWT 认证走正常权限校验
            err = _check_dept_scope(request, user)
            if err:
                return err
        if not user.avatar:
            return HttpResponse(status=404)
        try:
            client = get_minio_client()
            resp = client.get_object("avatar", user.avatar)
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            data = resp.read()
            resp.close()
            resp.release_conn()
            return HttpResponse(data, content_type=content_type)
        except Exception:
            return HttpResponse(status=404)
