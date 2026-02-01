package com.prypal.scanner

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class LoginActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        val passwordInput = findViewById<EditText>(R.id.password_input)
        val loginButton = findViewById<Button>(R.id.login_button)
        val status = findViewById<TextView>(R.id.login_status)

        loginButton.setOnClickListener {
            status.text = ""
            val password = passwordInput.text.toString().trim()
            if (password.isEmpty()) {
                status.text = "Introdu parola"
                return@setOnClickListener
            }

            FirestoreRepo.getSettings { settings ->
                val operatorPw = settings["operator_password"] as? String ?: "PryPass2026"
                val adminPw = settings["admin_password"] as? String ?: "PryAdmin2026"
                if (password == operatorPw || password == adminPw) {
                    startActivity(Intent(this, MaterialsActivity::class.java))
                    finish()
                } else {
                    runOnUiThread { status.text = "Parola incorecta" }
                }
            }
        }
    }
}
