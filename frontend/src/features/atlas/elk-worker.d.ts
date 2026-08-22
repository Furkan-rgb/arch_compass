/**
 * What `?worker` hands back, declared here rather than by pulling in `vite/client`.
 *
 * The suffix is a build-time instruction: it makes the bundler emit the module as its own
 * worker script and hand this file a constructor for it. The whole of `vite/client` is a
 * large ambient surface to add to `tsconfig` for one import, and this is the only one the
 * atlas has — so the one shape it needs is written out.
 */
declare module "*?worker" {
  const WorkerConstructor: new () => Worker;
  export default WorkerConstructor;
}
