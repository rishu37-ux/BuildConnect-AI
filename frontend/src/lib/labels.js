export const PROFESSIONS = {
  architect: 'Architect',
  structural_engineer: 'Structural engineer',
  contractor: 'Contractor',
  other: 'Other',
};

export const STATES = {
  punjab: 'Punjab',
  himachal_pradesh: 'Himachal Pradesh',
  chandigarh: 'Chandigarh',
  other: 'Other',
};

export const STATUSES = {
  new: { label: 'New', className: 'bg-sky-100 text-sky-800' },
  contacted: { label: 'Contacted', className: 'bg-amber-100 text-amber-800' },
  qualified: { label: 'Qualified', className: 'bg-violet-100 text-violet-800' },
  converted: { label: 'Converted', className: 'bg-emerald-100 text-emerald-800' },
  rejected: { label: 'Rejected', className: 'bg-slate-200 text-slate-700' },
};

export const formatPhone = (e164) =>
  e164 ? e164.replace(/^\+91(\d{5})(\d{5})$/, '+91 $1 $2') : '';
