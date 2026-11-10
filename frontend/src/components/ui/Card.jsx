import { cx } from '../../lib/cx'

export default function Card({ as: Component = 'div', className, children, ...props }) {
  return (
    <Component
      className={cx(
        'rounded-xl border border-slate-200 bg-white p-5 shadow-sm',
        className,
      )}
      {...props}
    >
      {children}
    </Component>
  )
}
