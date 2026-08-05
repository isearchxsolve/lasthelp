import React, { useState } from "react";

interface BookingConfirmProps {
  onConfirm: (details: { name: string; phone: string; email: string; date: string; time: string }) => void;
  onCancel: () => void;
  availableSlots: string[];
}

export const BookingConfirm: React.FC<BookingConfirmProps> = ({ onConfirm, onCancel, availableSlots }) => {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [selectedSlot, setSelectedSlot] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = "Name is required";
    if (!phone.trim() || !/^\+\d{10,15}$/.test(phone)) errs.phone = "Valid phone (+1234567890) required";
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = "Valid email required";
    if (!selectedSlot) errs.slot = "Please select a time slot";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    const [date, time] = selectedSlot.split("T");
    onConfirm({ name, phone, email, date, time });
  };

  return (
    <div className="booking-confirm-overlay">
      <div className="booking-confirm-modal">
        <h2>Book Appointment</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="booking-name">Full Name</label>
            <input
              id="booking-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="John Doe"
            />
            {errors.name && <span className="error">{errors.name}</span>}
          </div>
          <div className="form-group">
            <label htmlFor="booking-phone">Phone (+1234567890)</label>
            <input
              id="booking-phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1234567890"
            />
            {errors.phone && <span className="error">{errors.phone}</span>}
          </div>
          <div className="form-group">
            <label htmlFor="booking-email">Email</label>
            <input
              id="booking-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="john@example.com"
            />
            {errors.email && <span className="error">{errors.email}</span>}
          </div>
          <div className="form-group">
            <label>Available Slots</label>
            <div className="slots-grid">
              {availableSlots.map((slot) => (
                <button
                  key={slot}
                  type="button"
                  className={`slot-btn ${selectedSlot === slot ? "selected" : ""}`}
                  onClick={() => setSelectedSlot(slot)}
                >
                  {new Date(slot).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </button>
              ))}
            </div>
            {errors.slot && <span className="error">{errors.slot}</span>}
          </div>
          <div className="form-actions">
            <button type="button" className="btn-cancel" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="btn-confirm">
              Confirm Booking
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default BookingConfirm;
