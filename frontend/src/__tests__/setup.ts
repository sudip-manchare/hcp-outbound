import '@testing-library/jest-dom';

if (typeof window !== 'undefined') {
  HTMLDialogElement.prototype.showModal = HTMLDialogElement.prototype.showModal || function(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = HTMLDialogElement.prototype.close || function(this: HTMLDialogElement) {
    this.open = false;
  };
}
