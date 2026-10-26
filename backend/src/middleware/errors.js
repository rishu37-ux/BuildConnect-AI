import { ZodError } from 'zod';

export class HttpError extends Error {
  constructor(status, message, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

/** Parse `req[part]` with a zod schema and replace it with the parsed value. */
export const validate = (schema, part = 'body') => (req, _res, next) => {
  try {
    req[part === 'query' ? 'validatedQuery' : part] = schema.parse(req[part]);
    next();
  } catch (err) {
    next(err);
  }
};

export function notFound(_req, _res, next) {
  next(new HttpError(404, 'Not found'));
}

// eslint-disable-next-line no-unused-vars
export function errorHandler(err, _req, res, _next) {
  if (err instanceof ZodError) {
    return res.status(400).json({ error: 'Validation failed', details: err.flatten() });
  }
  if (err.code === '23505') {
    return res.status(409).json({ error: 'Duplicate record', details: err.detail });
  }
  const status = err.status ?? 500;
  if (status >= 500) console.error(err);
  res.status(status).json({ error: status >= 500 ? 'Internal server error' : err.message, details: err.details });
}
