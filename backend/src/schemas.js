import { z } from 'zod';

export const ROLES = ['admin', 'manager', 'sales', 'viewer'];
export const PROFESSIONS = ['architect', 'structural_engineer', 'contractor', 'other'];
export const STATUSES = ['new', 'contacted', 'qualified', 'converted', 'rejected'];
export const STATES = ['punjab', 'himachal_pradesh', 'chandigarh', 'other'];

const optionalText = (max) => z.string().trim().max(max).optional().nullable().transform((v) => v || null);

export const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export const createUserSchema = z.object({
  email: z.string().email(),
  full_name: z.string().trim().min(1).max(200),
  password: z.string().min(10).max(200),
  role: z.enum(ROLES).default('viewer'),
});

export const updateUserSchema = z.object({
  full_name: z.string().trim().min(1).max(200).optional(),
  role: z.enum(ROLES).optional(),
  is_active: z.boolean().optional(),
  password: z.string().min(10).max(200).optional(),
});

const bool = z.enum(['true', 'false']).transform((v) => v === 'true').optional();

export const leadFilterSchema = z.object({
  q: z.string().trim().max(200).optional(),
  state: z.enum(STATES).optional(),
  profession: z.enum(PROFESSIONS).optional(),
  status: z.enum(STATUSES).optional(),
  city: z.string().trim().max(100).optional(),
  assignedTo: z.union([z.literal('unassigned'), z.string().regex(/^\d+$/)]).optional(),
  hasPhone: bool,
  hasEmail: bool,
  sort: z.string().optional(),
  order: z.enum(['asc', 'desc']).optional(),
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(200).default(25),
});

export const updateLeadSchema = z.object({
  full_name: z.string().trim().min(1).max(200).optional(),
  firm_name: optionalText(200),
  profession: z.enum(PROFESSIONS).optional(),
  city: optionalText(100),
  district: optionalText(100),
  state: z.enum(STATES).optional(),
  status: z.enum(STATUSES).optional(),
  notes: optionalText(5000),
  assigned_to: z.number().int().positive().nullable().optional(),
}).strict();

export const ingestLeadSchema = z.object({
  full_name: z.string().trim().min(1).max(200),
  firm_name: optionalText(200),
  profession: z.enum(PROFESSIONS).default('other'),
  phone: optionalText(40),
  email: optionalText(254),
  city: optionalText(100),
  district: optionalText(100),
  state: z.enum(STATES).default('other'),
  website: optionalText(500),
  source_url: z.string().url().max(2000),
  confidence: z.number().min(0).max(1).default(0.5),
});

export const ingestBatchSchema = z.object({
  run_id: z.number().int().positive().optional(),
  leads: z.array(ingestLeadSchema).min(1).max(500),
});

export const startRunSchema = z.object({
  agent_name: z.string().min(1).max(100),
  target: z.record(z.any()).default({}),
});

export const finishRunSchema = z.object({
  pages_fetched: z.number().int().min(0),
  leads_found: z.number().int().min(0),
  stats: z.record(z.any()).default({}),
});

export const suppressionSchema = z.object({
  value: z.string().trim().min(3).max(254),
  reason: optionalText(500),
});
