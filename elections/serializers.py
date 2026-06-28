from rest_framework import serializers
from .models import User, Election, Candidate, Vote, VoterRegister, AuditLog
import random
import string


def generate_secret_code():
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(random.choices(chars, k=8))
        if not VoterRegister.objects.filter(secret_code=code).exists():
            return code


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'voter_id', 'is_voter', 'is_admin_user', 'is_staff',
                  'is_superuser', 'is_active_voter', 'phone_number']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']

    def create(self, validated_data):
        return User.objects.create_user(**validated_data, is_voter=True)


class VoterRegisterSerializer(serializers.ModelSerializer):
    registered_username = serializers.SerializerMethodField()

    class Meta:
        model = VoterRegister
        fields = ['id', 'full_name', 'phone_number', 'secret_code',
                  'is_used', 'is_active', 'created_at', 'registered_username']
        read_only_fields = ['is_used', 'created_at', 'secret_code']

    def get_registered_username(self, obj):
        if obj.registered_user:
            return obj.registered_user.username
        return None

    def create(self, validated_data):
        validated_data['secret_code'] = generate_secret_code()
        return super().create(validated_data)


class CandidateSerializer(serializers.ModelSerializer):
    vote_count = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = ['id', 'election', 'full_name', 'party', 'bio',
                  'photo', 'photo_url_direct', 'photo_url',
                  'display_order', 'vote_count']

    def get_vote_count(self, obj):
        return obj.votes.count()

    def get_photo_url(self, obj):
        # First check direct Cloudinary URL (uploaded from frontend)
        if obj.photo_url_direct:
            return obj.photo_url_direct
        # Fallback to file upload
        if not obj.photo:
            return None
        try:
            url = str(obj.photo.url)
            if url.startswith('http'):
                return url
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None


class ElectionSerializer(serializers.ModelSerializer):
    candidates = CandidateSerializer(many=True, read_only=True)
    total_votes = serializers.SerializerMethodField()

    class Meta:
        model = Election
        fields = ['id', 'title', 'description', 'start_date', 'end_date',
                  'status', 'created_at', 'candidates', 'total_votes']

    def get_total_votes(self, obj):
        return obj.votes.count()


class VoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vote
        fields = ['id', 'election', 'candidate', 'cast_at']
        read_only_fields = ['cast_at']

    def create(self, validated_data):
        validated_data['voter'] = self.context['request'].user
        return super().create(validated_data)


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'action', 'username', 'ip_address', 'details',
                  'election', 'timestamp']