import clsx from 'clsx'

export default function PageHeader({ title, description, actions, className }) {
  return (
    <div className={clsx('mb-5 flex flex-wrap items-start justify-between gap-3', className)}>
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
