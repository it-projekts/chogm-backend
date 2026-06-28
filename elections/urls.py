from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/verify-code/', views.VerifySecretCodeView.as_view(), name='verify-code'),
    path('auth/token/', views.CustomTokenObtainPairView.as_view(), name='token_obtain'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/profile/', views.ProfileView.as_view(), name='profile'),
    path('auth/change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('candidates/<int:pk>/photo/', views.UpdateCandidatePhotoView.as_view(), name='candidate-photo'),


    path('elections/', views.ElectionListCreateView.as_view(), name='elections'),
    path('elections/<int:pk>/', views.ElectionDetailView.as_view(), name='election-detail'),

    path('candidates/', views.CandidateListCreateView.as_view(), name='candidates'),
    path('candidates/<int:pk>/', views.CandidateDetailView.as_view(), name='candidate-detail'),

    path('votes/cast/', views.CastVoteView.as_view(), name='cast-vote'),
    path('votes/my/', views.MyVotesView.as_view(), name='my-votes'),

    path('voter-register/', views.VoterRegisterListCreateView.as_view(), name='voter-register'),
    path('voter-register/bulk/', views.BulkVoterUploadView.as_view(), name='voter-bulk'),
    path('voter-register/<int:pk>/', views.VoterRegisterDetailView.as_view(), name='voter-register-detail'),
    path('voter-register/<int:pk>/toggle/', views.ToggleVoterActiveView.as_view(), name='voter-toggle'),

    path('audit-log/', views.AuditLogListView.as_view(), name='audit-log'),
    path('dashboard/stats/', views.DashboardStatsView.as_view(), name='dashboard-stats'),
]