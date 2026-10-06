import type { components } from './generated/backend';
import { api, dataOrThrow } from './transport';

export type AuthSession = components['schemas']['AuthSessionResponse'];
export type RegisterInput = components['schemas']['RegisterRequest'];
export type LoginInput = components['schemas']['LoginRequest'];
export type PasswordInput = components['schemas']['ChangePasswordRequest'];

export const getSession = async () => dataOrThrow(await api.GET('/api/v1/auth/session'));
export const register = async (body: RegisterInput) =>
  dataOrThrow(await api.POST('/api/v1/auth/register', { body }));
export const login = async (body: LoginInput) =>
  dataOrThrow(await api.POST('/api/v1/auth/login', { body }));
export const logout = async () => dataOrThrow(await api.POST('/api/v1/auth/logout'));
export const updateProfile = async (body: components['schemas']['UpdateProfileRequest']) =>
  dataOrThrow(await api.PATCH('/api/v1/auth/profile', { body }));
export const changePassword = async (body: PasswordInput) =>
  dataOrThrow(await api.POST('/api/v1/auth/password', { body }));
export const forgotPassword = async (body: components['schemas']['EmailRequest']) =>
  dataOrThrow(await api.POST('/api/v1/auth/forgot-password', { body }));
export const resetPassword = async (body: components['schemas']['ResetPasswordRequest']) =>
  dataOrThrow(await api.POST('/api/v1/auth/reset-password', { body }));
