from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db import IntegrityError
from django.utils import timezone
from django.conf import settings
from .models import User, Election, Candidate, Vote, VoterRegister, AuditLog
from .serializers import (
    UserSerializer, RegisterSerializer,
    ElectionSerializer, CandidateSerializer,
    VoteSerializer, VoterRegisterSerializer,
    AuditLogSerializer, generate_secret_code
)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR', '')


def log_action(action, user=None, username='', ip='', details='', election=None):
    try:
        AuditLog.objects.create(
            action=action,
            user=user,
            username=username or (user.username if user else ''),
            ip_address=ip,
            details=details,
            election=election,
        )
    except Exception as e:
        print(f"Audit log error: {e}")


def send_sms(phone, message):
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone
        )
        return True
    except Exception as e:
        print(f"SMS error: {e}")
        return False


class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        username = request.data.get('username', '')
        try:
            response = super().post(request, *args, **kwargs)
            if response.status_code == 200:
                try:
                    user = User.objects.get(username=username)
                    log_action('login_success', user=user, username=username, ip=ip,
                               details=f'Successful login from {ip}')
                except User.DoesNotExist:
                    pass
            return response
        except Exception:
            log_action('login_failed', username=username, ip=ip,
                       details=f'Failed login attempt from {ip}')
            raise


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        secret_code = request.data.get('secret_code')
        username = request.data.get('username')
        password = request.data.get('password')
        confirm_password = request.data.get('confirm_password')
        ip = get_client_ip(request)

        if not secret_code:
            return Response({'error': 'Secret code is required'}, status=400)

        try:
            voter_record = VoterRegister.objects.get(secret_code=secret_code)
        except VoterRegister.DoesNotExist:
            log_action('login_failed', username=secret_code, ip=ip,
                       details=f'Invalid secret code used: {secret_code}')
            return Response({'error': 'No records found'}, status=404)

        if voter_record.is_used:
            return Response({'error': 'This secret code has already been used'}, status=400)

        if not voter_record.is_active:
            return Response({'error': 'This voter record has been deactivated'}, status=400)

        if not username or not password:
            return Response({
                'step': 'complete',
                'full_name': voter_record.full_name,
                'message': 'Secret code verified'
            }, status=200)

        if password != confirm_password:
            return Response({'error': 'Passwords do not match'}, status=400)

        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already taken'}, status=400)

        full_name_parts = voter_record.full_name.split(' ', 1)
        first_name = full_name_parts[0]
        last_name = full_name_parts[1] if len(full_name_parts) > 1 else ''

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=voter_record.phone_number,
            is_voter=True,
            is_active=True,
        )

        voter_record.is_used = True
        voter_record.registered_user = user
        voter_record.save()

        log_action('voter_registered', user=user, username=username, ip=ip,
                   details=f'{voter_record.full_name} registered successfully')

        return Response({'message': 'Registration successful! You can now log in.'}, status=201)


class VerifySecretCodeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        secret_code = request.data.get('secret_code')
        if not secret_code:
            return Response({'error': 'Secret code is required'}, status=400)
        try:
            voter_record = VoterRegister.objects.get(secret_code=secret_code)
            if voter_record.is_used:
                return Response({'error': 'This secret code has already been used'}, status=400)
            if not voter_record.is_active:
                return Response({'error': 'This voter record has been deactivated'}, status=400)
            return Response({'valid': True, 'full_name': voter_record.full_name}, status=200)
        except VoterRegister.DoesNotExist:
            return Response({'error': 'No records found'}, status=404)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            return Response({
                'id': user.id,
                'username': user.username,
                'email': user.email or '',
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'voter_id': user.voter_id or '',
                'is_staff': bool(user.is_staff),
                'is_superuser': bool(user.is_superuser),
                'is_voter': bool(user.is_voter),
                'is_active_voter': bool(getattr(user, 'is_active_voter', True)),
                'phone_number': getattr(user, 'phone_number', '') or '',
            })
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    def patch(self, request):
        try:
            user = request.user
            user.first_name = request.data.get('first_name', user.first_name)
            user.last_name = request.data.get('last_name', user.last_name)
            user.email = request.data.get('email', user.email)
            user.save()
            return Response({'message': 'Profile updated successfully'})
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user
            old_password = request.data.get('old_password')
            new_password = request.data.get('new_password')
            if not user.check_password(old_password):
                return Response({'error': 'Current password is incorrect'}, status=400)
            if len(new_password) < 6:
                return Response({'error': 'Password must be at least 6 characters'}, status=400)
            user.set_password(new_password)
            user.save()
            return Response({'message': 'Password changed successfully'})
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class ElectionListCreateView(generics.ListCreateAPIView):
    serializer_class = ElectionSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        try:
            user = self.request.user
            if user.is_staff:
                return Election.objects.all().order_by('-created_at')
            return Election.objects.filter(
                status__in=['active', 'closed']
            ).order_by('-created_at')
        except Exception:
            return Election.objects.none()

    def get_serializer_context(self):
        return {'request': self.request}

    def perform_create(self, serializer):
        election = serializer.save()
        log_action('election_created', user=self.request.user,
                   username=self.request.user.username,
                   ip=get_client_ip(self.request),
                   details=f'Election "{election.title}" created',
                   election=election)


class ElectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Election.objects.all()
    serializer_class = ElectionSerializer

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_serializer_context(self):
        return {'request': self.request}

    def perform_update(self, serializer):
        old_status = self.get_object().status
        election = serializer.save()
        new_status = election.status
        if old_status != new_status:
            action = 'election_activated' if new_status == 'active' else 'election_closed'
            log_action(action, user=self.request.user,
                       username=self.request.user.username,
                       ip=get_client_ip(self.request),
                       details=f'Election "{election.title}" changed to {new_status}',
                       election=election)


class CandidateListCreateView(generics.ListCreateAPIView):
    serializer_class = CandidateSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        election_id = self.request.query_params.get('election_id')
        if election_id:
            return Candidate.objects.filter(election_id=election_id)
        return Candidate.objects.all()

    def get_serializer_context(self):
        return {'request': self.request}


class CandidateDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Candidate.objects.all()
    serializer_class = CandidateSerializer

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_serializer_context(self):
        return {'request': self.request}


class UpdateCandidatePhotoView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            photo_url = request.data.get('photo_url_direct', '')
            print(f"UpdatePhoto: pk={pk}, url={photo_url}")
            rows = Candidate.objects.filter(pk=pk).update(
                photo_url_direct=photo_url
            )
            print(f"UpdatePhoto: rows updated={rows}")
            candidate = Candidate.objects.get(pk=pk)
            print(f"UpdatePhoto: saved value={candidate.photo_url_direct}")
            return Response({
                'message': 'Photo updated successfully',
                'photo_url_direct': candidate.photo_url_direct,
                'photo_url': candidate.photo_url_direct,
            })
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate not found'}, status=404)
        except Exception as e:
            print(f"UpdatePhoto Error: {e}")
            return Response({'error': str(e)}, status=500)


class CastVoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            ip = get_client_ip(request)
            if not getattr(request.user, 'is_active_voter', True):
                return Response({'error': 'Your voter account has been deactivated'}, status=403)

            election_id = request.data.get('election_id')
            candidate_id = request.data.get('candidate_id')

            if not election_id or not candidate_id:
                return Response({'error': 'election_id and candidate_id are required'}, status=400)

            try:
                election = Election.objects.get(pk=election_id)
            except Election.DoesNotExist:
                return Response({'error': 'Election not found'}, status=404)

            if election.status != 'active':
                return Response({'error': 'This election is not active'}, status=400)

            if timezone.now() > election.end_date:
                return Response({'error': 'This election has ended'}, status=400)

            try:
                candidate = Candidate.objects.get(pk=candidate_id, election=election)
            except Candidate.DoesNotExist:
                return Response({'error': 'Candidate not found'}, status=404)

            try:
                vote = Vote.objects.create(
                    voter=request.user,
                    election=election,
                    candidate=candidate
                )
                log_action('vote_cast', user=request.user,
                           username=request.user.username,
                           ip=ip,
                           details=f'Vote cast in "{election.title}"',
                           election=election)
                return Response({
                    'message': f'Vote cast successfully for {candidate.full_name}',
                    'cast_at': vote.cast_at
                }, status=201)
            except IntegrityError:
                return Response({'error': 'You have already voted in this election'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class MyVotesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            votes = Vote.objects.filter(voter=request.user).select_related('election', 'candidate')
            data = []
            for vote in votes:
                data.append({
                    'election': vote.election.title,
                    'election_id': vote.election.id,
                    'candidate': vote.candidate.full_name,
                    'party': vote.candidate.party,
                    'cast_at': vote.cast_at,
                })
            return Response(data)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class VoterRegisterListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = VoterRegisterSerializer
    queryset = VoterRegister.objects.all().order_by('-created_at')

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action('voter_registered', user=self.request.user,
                   username=self.request.user.username,
                   ip=get_client_ip(self.request),
                   details=f'Voter "{instance.full_name}" added to register')
        phone = instance.phone_number
        message = (
            f"Hello {instance.full_name},\n"
            f"Your CHOGM 16th - INT secret voting code is: {instance.secret_code}\n"
            f"Use this code to register and vote. Do not share it."
        )
        send_sms(phone, message)


class VoterRegisterDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = VoterRegisterSerializer
    queryset = VoterRegister.objects.all()

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            full_name = instance.full_name
            if instance.registered_user:
                Vote.objects.filter(voter=instance.registered_user).delete()
                instance.registered_user.delete()
            instance.delete()
            log_action('voter_deactivated', user=request.user,
                       username=request.user.username,
                       ip=get_client_ip(request),
                       details=f'Voter "{full_name}" permanently deleted')
            return Response({'message': 'Voter deleted successfully'}, status=204)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class BulkVoterUploadView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            voters_data = request.data.get('voters', [])
            if not voters_data:
                return Response({'error': 'No voter data provided'}, status=400)

            created = []
            errors = []
            for i, voter in enumerate(voters_data):
                full_name = voter.get('full_name', '').strip()
                phone_number = voter.get('phone_number', '').strip()

                if not full_name or not phone_number:
                    errors.append(f"Row {i+1}: Missing full name or phone number")
                    continue

                try:
                    secret_code = generate_secret_code()
                    instance = VoterRegister.objects.create(
                        full_name=full_name,
                        phone_number=phone_number,
                        secret_code=secret_code,
                    )
                    created.append({
                        'full_name': full_name,
                        'phone_number': phone_number,
                        'secret_code': secret_code,
                    })
                    message = (
                        f"Hello {full_name},\n"
                        f"Your CHOGM 16th - INT secret voting code is: {secret_code}\n"
                        f"Use this code to register and vote. Do not share it."
                    )
                    send_sms(phone_number, message)
                except Exception as e:
                    errors.append(f"Row {i+1}: {str(e)}")

            log_action('bulk_upload', user=request.user,
                       username=request.user.username,
                       ip=get_client_ip(request),
                       details=f'Bulk upload: {len(created)} voters added, {len(errors)} errors')

            return Response({
                'message': f'{len(created)} voters added successfully',
                'created': created,
                'errors': errors,
            }, status=201)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class ToggleVoterActiveView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            voter = VoterRegister.objects.get(pk=pk)
            voter.is_active = not voter.is_active
            voter.save()
            if voter.registered_user:
                voter.registered_user.is_active_voter = voter.is_active
                voter.registered_user.save()
            action = 'voter_activated' if voter.is_active else 'voter_deactivated'
            log_action(action, user=request.user,
                       username=request.user.username,
                       ip=get_client_ip(request),
                       details=f'Voter "{voter.full_name}" {"activated" if voter.is_active else "deactivated"}')
            return Response({
                'message': f'Voter {"activated" if voter.is_active else "deactivated"} successfully',
                'is_active': voter.is_active
            })
        except VoterRegister.DoesNotExist:
            return Response({'error': 'Voter not found'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class AuditLogListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        queryset = AuditLog.objects.all().order_by('-timestamp')
        action = self.request.query_params.get('action')
        election_id = self.request.query_params.get('election_id')
        if action:
            queryset = queryset.filter(action=action)
        if election_id:
            queryset = queryset.filter(election_id=election_id)
        return queryset[:200]


class DashboardStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            return Response({
                'total_elections': Election.objects.count(),
                'active_elections': Election.objects.filter(status='active').count(),
                'total_voters': VoterRegister.objects.count(),
                'registered_voters': VoterRegister.objects.filter(is_used=True).count(),
                'total_votes': Vote.objects.count(),
                'recent_elections': ElectionSerializer(
                    Election.objects.order_by('-created_at')[:5],
                    many=True,
                    context={'request': request}
                ).data,
                'recent_voters': VoterRegisterSerializer(
                    VoterRegister.objects.order_by('-created_at')[:5],
                    many=True
                ).data,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=500)