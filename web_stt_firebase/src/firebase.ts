// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyCaN8MEdrW5_g6aCauCJTidrZfW8Cy5Me0",
  authDomain: "rokey-cobot2.firebaseapp.com",
  projectId: "rokey-cobot2",
  storageBucket: "rokey-cobot2.firebasestorage.app",
  messagingSenderId: "234950911213",
  appId: "1:234950911213:web:b31885e746eb8aab1e98e4"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
