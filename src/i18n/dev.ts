/** Build-time dev flag for the i18n runtime.
    Kept in a JSX-free module: vite's import.meta.env rewrite must not share
    a transform with plugin-react's preamble injection (magic-string chunk
    conflict). index.tsx imports this instead of touching import.meta itself. */
export const I18N_DEV: boolean = import.meta.env.DEV
